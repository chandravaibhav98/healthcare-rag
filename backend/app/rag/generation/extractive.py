"""Extractive answer generator (plan §4 Phase 2).

The answer is assembled only from verbatim source sentences (or list items or table
rows) of the retrieved chunks. Nothing is paraphrased, which keeps the answer auditable
and deterministic. ADR-0002 explains why token coverage alone cannot then serve as
confidence.

Candidate score (all components in [0, 1]):

    score = 0.45 · lexical   IDF-weighted share of query terms found in the sentence
          + 0.20 · dense     cosine(sentence, query) in the hashed embedding space
          + 0.15 · type      1 if the sentence has the answer type the question asks for
                             (duration, frequency, temperature, quantity, timing, steps)
          + 0.10 · section   IDF-weighted share of query terms in the chunk title/section path
          + 0.10 · prior     the chunk's fused retrieval score

Selection is greedy MMR (Carbonell & Goldstein, 1998):
    pick argmax  λ · score - (1 - λ) · max_jaccard(candidate, already selected)
stopping at `max_sentences` or once a candidate's score falls below
`min_relative_score × best score`. Selected sentences are then emitted in retrieval-rank
order, and in document order within a chunk, each followed by its `[n]` marker.

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
from app.rag.generation.answer_types import detect_answer_types, matches_answer_type
from app.rag.ingestion.sentences import sentence_spans
from app.rag.pipeline import LoadedIndex
from app.rag.retrieval.expansion import QueryExpander

W_LEXICAL: Final = 0.45
W_DENSE: Final = 0.20
W_TYPE: Final = 0.15
W_SECTION: Final = 0.10
W_PRIOR: Final = 0.10
MIN_CANDIDATE_TOKENS: Final = 4

_LIST_ITEM: Final = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_TABLE_SEPARATOR: Final = re.compile(r"^\|[\s:|-]+\|$")
_TERMINAL: Final = re.compile(r"[.!?]$")


@dataclass(frozen=True, slots=True)
class _Candidate:
    hit_pos: int  # position of the source chunk in the retrieved list (0-based)
    start: int
    end: int
    text: str
    terms: frozenset[str]
    is_list_item: bool


def _candidates(hit_pos: int, text: str) -> list[_Candidate]:
    """Split chunk text into answerable units with spans into the original text."""
    units: list[tuple[int, int, str, bool]] = []
    offset = 0
    lines = text.split("\n")
    table_row = 0
    for idx, line in enumerate(lines):
        line_start = offset
        offset += len(line) + 1
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
        if stripped.endswith(":") and count_tokens(stripped) <= 8:
            continue  # inline sub-heading such as "Monitoring Details:"
        for s, e in sentence_spans(line):
            units.append((line_start + s, line_start + e, line[s:e], False))
    return [
        _Candidate(hit_pos, s, e, t, frozenset(analyze(t)), item)
        for s, e, t, item in units
        if count_tokens(t) >= MIN_CANDIDATE_TOKENS
    ]


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


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
