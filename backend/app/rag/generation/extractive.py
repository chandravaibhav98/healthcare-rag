"""Extractive answer generator (plan §4 Phase 2).

The answer is assembled only from verbatim source sentences (or list items, lead-in +
list blocks, or table rows) of the retrieved chunks. Nothing is paraphrased, which
keeps the answer auditable and deterministic. ADR-0002 explains why token coverage
alone cannot then serve as confidence.

Candidate score (all components in [0, 1]):

    score = 0.45 · lexical   IDF-weighted share of query terms found in the sentence
          + 0.20 · dense     cosine(sentence, query) in the hashed embedding space
          + 0.15 · type      1 if the sentence has the answer type the question asks for
                             (duration, frequency, temperature, quantity, timing, steps)
          + 0.10 · section   IDF-weighted share of query terms in the chunk title/section path
          + 0.10 · prior     the chunk's fused retrieval score

Value-type gate (manual-test finding F-03), OFF by default: when enabled and the question
asks for a temperature, a duration or a frequency, only candidates that state such a value
may enter the answer. It fixes F-03 ("what temperature range…" answered with a sentence
that only echoes "temperature range") but, on the dev pool, it also drops correct negative
answers ("do not change ventilator circuits routinely") and is triggered by questions that
merely mention a temperature ("after a temperature excursion"). Its focused answers also
expose F-04: confidence takes the max over cited chunks, so dropping an irrelevant
citation can lower it. Both are re-tuned on the dev split in the Phase 4 re-test.

Selection is greedy MMR (Carbonell & Goldstein, 1998):
    pick argmax  λ · score - (1 - λ) · max_jaccard(candidate, already selected)
stopping at `max_sentences` or once a candidate's score falls below
`min_relative_score × best score`. A candidate whose span overlaps one already chosen
(a list item inside a chosen list block, or the reverse) is skipped. Selected units are
then emitted in retrieval-rank order, and in document order within a chunk, each
followed by its `[n]` marker.

A sentence ending in ":" is a lead-in ("... at five moments during care:"). It is
never an answer on its own: together with the list that follows it, it forms one unit;
with no list after it (e.g. the list fell into the next chunk), it is dropped.

Superseded guidance never becomes answer text (ADR-0010). Superseded chunks stay in the
retrieved evidence so a reviewer can see them, but no sentence is extracted from them.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np

from app.domain.models import AnswerSentence, CitedChunk, GeneratedAnswer, RetrievedChunk
from app.rag.analysis import analyze, count_tokens
from app.rag.generation.answer_types import (
    AnswerType,
    detect_answer_types,
    matches_answer_type,
)
from app.rag.ingestion.sentences import sentence_spans
from app.rag.pipeline import LoadedIndex
from app.rag.retrieval.expansion import QueryExpander

W_LEXICAL: Final = 0.45
W_DENSE: Final = 0.20
W_TYPE: Final = 0.15
W_SECTION: Final = 0.10
W_PRIOR: Final = 0.10
MIN_CANDIDATE_TOKENS: Final = 4

# Answer types whose sentence cue is specific enough to be a hard requirement (F-03).
GATED_ANSWER_TYPES: Final = frozenset({"temperature", "duration", "frequency"})

_LIST_ITEM: Final = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_TABLE_SEPARATOR: Final = re.compile(r"^\|[\s:|-]+\|$")
_TERMINAL: Final = re.compile(r"[.!?]$")


@dataclass(frozen=True, slots=True)
class _Candidate:
    # position of the source chunk in the retrieved list (0-based)
    hit_pos: int
    start: int
    end: int
    text: str
    terms: frozenset[str]
    is_list_item: bool


def _line_starts(lines: list[str]) -> list[int]:
    starts: list[int] = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line) + 1
    return starts


def _list_block_end(lines: list[str], starts: list[int], idx: int) -> int | None:
    """End offset of the list directly after line `idx` (blank lines allowed), else None."""
    end: int | None = None
    for j in range(idx + 1, len(lines)):
        line = lines[j]
        if _LIST_ITEM.match(line):
            end = starts[j] + len(line)
        elif end is not None and line.startswith((" ", "\t")) and line.strip():
            end = starts[j] + len(line)  # continuation of the previous item
        elif line.strip():
            break  # a paragraph: the list (if any) has ended
    return end


def _candidates(hit_pos: int, text: str) -> list[_Candidate]:
    """Split chunk text into answerable units with spans into the original text."""
    units: list[tuple[int, int, str, bool]] = []
    lines = text.split("\n")
    starts = _line_starts(lines)
    table_row = 0
    for idx, line in enumerate(lines):
        line_start = starts[idx]
        stripped = line.strip()
        if not stripped:
            table_row = 0
            continue
        if stripped.startswith("|"):
            table_row += 1
            if table_row == 1 or _TABLE_SEPARATOR.match(stripped):
                continue  # header and separator rows are not answers on their own
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            units.append(
                (line_start, line_start + len(line), ": ".join(c for c in cells if c), False)
            )
            continue
        table_row = 0
        if m := _LIST_ITEM.match(line):
            end = line_start + len(line)
            # Absorb indented continuation lines that belong to this item.
            j = idx + 1
            while j < len(lines) and lines[j].startswith((" ", "\t")) and lines[j].strip():
                if _LIST_ITEM.match(lines[j]):
                    break
                end += len(lines[j]) + 1
                j += 1
            units.append(
                (line_start, end, " ".join(text[line_start + m.end() : end].split()), True)
            )
            continue
        if line.startswith((" ", "\t")):
            continue  # continuation already absorbed by its list item
        spans = sentence_spans(line)
        if stripped.endswith(":") and spans:
            *spans, lead = spans
            block_end = _list_block_end(lines, starts, idx)
            if block_end is not None:
                block_start = line_start + lead[0]
                units.append(
                    (block_start, block_end, " ".join(text[block_start:block_end].split()), True)
                )
        for s, e in spans:
            units.append((line_start + s, line_start + e, line[s:e], False))
    return [
        _Candidate(hit_pos, s, e, t, frozenset(analyze(t)), item)
        for s, e, t, item in units
        if count_tokens(t) >= MIN_CANDIDATE_TOKENS
    ]


def _gate_by_value_type(
    scored: list[tuple[float, _Candidate]], answer_types: tuple[AnswerType, ...]
) -> list[tuple[float, _Candidate]]:
    """Keep only candidates stating the value the question asks for, if any do (F-03).

    Order is preserved, so the deterministic sort that follows is unaffected. An empty
    result never happens: with no matching candidate the input is returned unchanged.
    """
    gated = tuple(t for t in answer_types if t.name in GATED_ANSWER_TYPES)
    if not gated:
        return scored
    typed = [
        p for p in scored if matches_answer_type(gated, p[1].text, is_list_item=p[1].is_list_item)
    ]
    return typed or scored


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _overlaps(a: _Candidate, b: _Candidate) -> bool:
    return a.hit_pos == b.hit_pos and a.start < b.end and b.start < a.end


def _with_marker(sentence: str, citation_id: int) -> str:
    """'... gloves.' → '... gloves [1].' (the marker sits before terminal punctuation)."""
    sentence = sentence.rstrip()
    if _TERMINAL.search(sentence):
        return f"{sentence[:-1]} [{citation_id}]{sentence[-1]}"
    return f"{sentence} [{citation_id}]."


class ExtractiveGenerator:
    def __init__(
        self,
        index: LoadedIndex,
        *,
        expander: QueryExpander | None = None,
        max_sentences: int = 3,
        mmr_lambda: float = 0.7,
        min_relative_score: float = 0.5,
        value_type_gate: bool = False,
    ) -> None:
        if (
            max_sentences < 1
            or not 0.0 <= mmr_lambda <= 1.0
            or not 0.0 <= min_relative_score <= 1.0
        ):
            raise ValueError("invalid generator configuration")
        self._index = index
        self._expander = expander
        self._max = max_sentences
        self._lambda = mmr_lambda
        self._min_rel = min_relative_score
        # Off by default until the Phase 4 re-test (F-03/F-04, docstring). On for ablation.
        self._value_type_gate = value_type_gate

    def _weighted_share(self, query_terms: frozenset[str], terms: frozenset[str]) -> float:
        bm25 = self._index.bm25
        total = sum(bm25.idf(t) for t in query_terms)
        return sum(bm25.idf(t) for t in query_terms & terms) / total if total else 0.0

    def generate(self, question: str, evidence: Sequence[RetrievedChunk]) -> GeneratedAnswer:
        query = self._expander.expand(question).text if self._expander else question
        q_terms = frozenset(analyze(query))
        answer_types = detect_answer_types(question)
        cands = [
            c
            for pos, hit in enumerate(evidence)
            if not hit.chunk.superseded
            for c in _candidates(pos, hit.chunk.text)
        ]
        if not q_terms or not cands:
            return GeneratedAnswer(text="", sentences=(), citations=())

        embedder = self._index.embedder
        q_vec = embedder.embed([query])[0]
        dense = np.clip(embedder.embed([c.text for c in cands]) @ q_vec, 0.0, 1.0)

        scored: list[tuple[float, _Candidate]] = []
        for cand, dense_sim in zip(cands, dense, strict=True):
            lexical = self._weighted_share(q_terms, cand.terms)
            if lexical == 0.0:
                continue  # must share at least one query term to be considered
            hit = evidence[cand.hit_pos]
            section = self._weighted_share(
                q_terms, frozenset(analyze(f"{hit.chunk.title} {hit.chunk.section}"))
            )
            type_match = matches_answer_type(
                answer_types, cand.text, is_list_item=cand.is_list_item
            )
            score = (
                W_LEXICAL * lexical
                + W_DENSE * float(dense_sim)
                + W_TYPE * float(type_match)
                + W_SECTION * section
                + W_PRIOR * hit.score
            )
            scored.append((round(score, 9), cand))
        if not scored:
            return GeneratedAnswer(text="", sentences=(), citations=())
        if self._value_type_gate:
            scored = _gate_by_value_type(scored, answer_types)

        scored.sort(key=lambda p: (-p[0], p[1].hit_pos, p[1].start))
        best = scored[0][0]
        selected: list[tuple[float, _Candidate]] = []
        seen_texts: set[str] = set()
        pool = [p for p in scored if p[0] >= self._min_rel * best]
        while pool and len(selected) < self._max:

            def mmr(p: tuple[float, _Candidate]) -> float:
                redundancy = max((_jaccard(p[1].terms, s.terms) for _, s in selected), default=0.0)
                return round(self._lambda * p[0] - (1 - self._lambda) * redundancy, 9)

            choice = max(pool, key=lambda p: (mmr(p), -p[1].hit_pos, -p[1].start))
            pool.remove(choice)
            key = " ".join(choice[1].text.lower().split())
            if key in seen_texts:
                continue  # identical sentence repeated through chunk overlap
            if any(_overlaps(choice[1], s) for _, s in selected):
                continue  # already said: an item inside a chosen list block, or the reverse
            seen_texts.add(key)
            selected.append(choice)

        selected.sort(key=lambda p: (p[1].hit_pos, p[1].start))
        citation_of: dict[int, int] = {}
        spans: dict[int, list[tuple[int, int]]] = {}
        sentences: list[AnswerSentence] = []
        for score, cand in selected:
            cid = citation_of.setdefault(cand.hit_pos, len(citation_of) + 1)
            spans.setdefault(cand.hit_pos, []).append((cand.start, cand.end))
            sentences.append(
                AnswerSentence(
                    text=cand.text,
                    chunk_id=evidence[cand.hit_pos].chunk.chunk_id,
                    start=cand.start,
                    end=cand.end,
                    citation_id=cid,
                    score=score,
                )
            )
        citations = tuple(
            CitedChunk(citation_id=cid, retrieved=evidence[pos], spans=tuple(spans[pos]))
            for pos, cid in sorted(citation_of.items(), key=lambda p: p[1])
        )
        text = " ".join(_with_marker(s.text, s.citation_id) for s in sentences)
        return GeneratedAnswer(text=text, sentences=tuple(sentences), citations=citations)
