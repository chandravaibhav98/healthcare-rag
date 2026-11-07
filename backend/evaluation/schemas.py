"""Gold-dataset schema (plan §4 Phase 0, relevance semantics from ADR-0001).

One JSONL line = one `GoldItem`. Fields beyond the plan's minimum set
(`topic`, `kind`) exist because Phase 4 needs them: `topic` for the stratified
dev/test split and the per-topic breakdown, and `kind` to report direct,
paraphrase/acronym and unanswerable questions separately.

Relevance (ADR-0001): a chunk is *relevant* iff it has a grade.
    grade 2 = answer-bearing (contains the facts needed for the answer)
    grade 1 = topically relevant (same guideline section, supporting context)
Precision@K counts both grades; nDCG@K uses the grades as gains.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from app.api.schemas.qa import Question
from app.domain.ids import ChunkId, Slug

Grade = Literal[1, 2]
GoldId = Annotated[str, StringConstraints(pattern=r"^q-\d{4}$")]
Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Split(StrEnum):
    DEV = "dev"
    TEST = "test"


class QuestionKind(StrEnum):
    DIRECT = "direct"
    PARAPHRASE = "paraphrase"
    ACRONYM = "acronym"
    UNANSWERABLE = "unanswerable"


class GoldItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: GoldId = Field(description="Stable question id, e.g. q-0001.")
    question: Question
    split: Split = Field(description="Tune on dev only; report on test (ADR-0002).")
    topic: Slug = Field(description="Topic slug used for stratification, e.g. hand-hygiene.")
    kind: QuestionKind
    answerable: bool = Field(
        description="False for out-of-scope/unsupported questions (abstention tests)."
    )
    relevant_chunk_ids: list[ChunkId] = Field(
        default_factory=list,
        description="All relevant chunks (grade 1 or 2). Order is not meaningful.",
    )
    grades: dict[ChunkId, Grade] = Field(
        default_factory=dict, description="Graded relevance per chunk; keys == relevant_chunk_ids."
    )
    expected_keywords: list[Keyword] = Field(
        default_factory=list,
        description="Terms a correct answer is expected to contain (diagnostics).",
    )

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if len(set(self.relevant_chunk_ids)) != len(self.relevant_chunk_ids):
            raise ValueError("relevant_chunk_ids must be unique")
        if set(self.grades) != set(self.relevant_chunk_ids):
            raise ValueError("grades must have exactly one entry per relevant chunk id")

        if self.answerable:
            if self.kind is QuestionKind.UNANSWERABLE:
                raise ValueError("kind=unanswerable contradicts answerable=true")
            if 2 not in self.grades.values():
                raise ValueError(
                    "an answerable item needs at least one answer-bearing (grade 2) chunk"
                )
        else:
            if self.kind is not QuestionKind.UNANSWERABLE:
                raise ValueError("answerable=false requires kind=unanswerable")
            if self.relevant_chunk_ids:
                raise ValueError("an unanswerable item must not list relevant chunks")
        return self


class GoldDatasetError(ValueError):
    """Raised with file:line context so annotation errors are quick to fix."""


def parse_gold_lines(lines: Iterable[str], source: str = "<memory>") -> list[GoldItem]:
    items: list[GoldItem] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            item = GoldItem.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise GoldDatasetError(f"{source}:{lineno}: {exc}") from exc
        if item.id in seen:
            raise GoldDatasetError(f"{source}:{lineno}: duplicate id {item.id}")
        seen.add(item.id)
        items.append(item)
    return items


def load_gold_jsonl(path: Path) -> list[GoldItem]:
    with path.open(encoding="utf-8") as fh:
        return parse_gold_lines(fh, source=str(path))
