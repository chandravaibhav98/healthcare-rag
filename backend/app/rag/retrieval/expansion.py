"""Deterministic acronym/synonym query expansion (ADR-0004).

Guideline questions are full of acronyms (PPE, AEFI, CLABSI) and lay paraphrases
("taking off gloves" for "doffing"). Hashed vectors and BM25 are both lexical, so a
small curated map recovers recall cheaply and reproducibly. No model, no randomness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final

from app.domain.models import ExpandedQuery
from app.rag.analysis import word_tokens

DEFAULT_MAP_PATH: Final = Path(__file__).with_name("query_expansions.json")


def _contains(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    n = len(phrase)
    return any(tuple(tokens[i : i + n]) == phrase for i in range(len(tokens) - n + 1))


@dataclass(frozen=True, slots=True)
class QueryExpander:
    # Each group: phrases (as token tuples) that are interchangeable, in file order.
    groups: tuple[tuple[tuple[str, ...], ...], ...]
    version: int

    @classmethod
    def from_file(cls, path: Path = DEFAULT_MAP_PATH) -> QueryExpander:
        return _load(path)

    def expand(self, question: str) -> ExpandedQuery:
        tokens = word_tokens(question)
        added: list[str] = []
        for group in self.groups:
            if not any(_contains(tokens, phrase) for phrase in group):
                continue
            for phrase in group:
                text = " ".join(phrase)
                if not _contains(tokens, phrase) and text not in added:
                    added.append(text)
        return ExpandedQuery(original=question, added_terms=tuple(added))

    def matched_groups(self, question: str) -> list[MatchedGroup]:
        tokens = word_tokens(question)
        out: list[MatchedGroup] = []
        for group in self.groups:
            matched = tuple(p for p in group if _contains(tokens, p))
            if matched:
                out.append(MatchedGroup(matched=matched, members=group))
        return out


@dataclass(frozen=True, slots=True)
class MatchedGroup:
    """A synonym/acronym group that a question mentions (used by query support)."""

    matched: tuple[tuple[str, ...], ...]  # phrases from the group found in the question
    members: tuple[tuple[str, ...], ...]  # every phrase in the group


@cache
def _load(path: Path) -> QueryExpander:
    data = json.loads(path.read_text(encoding="utf-8"))
    groups: list[tuple[tuple[str, ...], ...]] = []
    for acronym, expansion in data["acronyms"].items():
        groups.append((tuple(word_tokens(acronym)), tuple(word_tokens(expansion))))
    for members in data["synonyms"]:
        groups.append(tuple(tuple(word_tokens(m)) for m in members))
    return QueryExpander(groups=tuple(groups), version=int(data["version"]))
