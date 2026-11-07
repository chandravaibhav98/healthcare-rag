"""Core domain types for the indexing pipeline. Framework-free; no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.ids import DocId, Slug

SECTION_SEPARATOR = " › "


class SourceOrg(StrEnum):
    WHO = "WHO"
    NIH = "NIH"
    CDC = "CDC"


class DocStatus(StrEnum):
    CURRENT = "current"
    SUPERSEDED = "superseded"


class FrontMatter(BaseModel):
    """YAML front-matter every corpus document must carry (plan §4 Phase 1)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    doc_id: DocId
    title: str = Field(min_length=1)
    source_org: SourceOrg
    version: str = Field(pattern=r"^\d+(\.\d+){0,2}$")
    effective_date: date
    topic: list[Slug] = Field(min_length=1)
    audience: list[Slug] = Field(min_length=1)
    jurisdiction: Slug
    status: DocStatus = DocStatus.CURRENT
    supersedes: DocId | None = None
    # The corpus must be synthetic: real guidance could be mistaken for advice (risk R8).
    synthetic: Literal[True]


@dataclass(frozen=True, slots=True)
class Document:
    meta: FrontMatter
    body: str  # normalised Markdown body (NFC, LF, no front-matter)
    path: str  # POSIX path relative to the corpus root, e.g. "who/who-hh-001.md"
    sha256: str  # of the normalised full text, so CRLF/LF checkouts hash identically

    @property
    def doc_id(self) -> str:
        return self.meta.doc_id


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    doc_id: str
    section_path: tuple[str, ...]
    section_slug: str
    ordinal: int  # 1-based within (doc_id, section_slug)
    text: str
    token_count: int
    has_overlap: bool  # starts with sentences carried over from the previous chunk
    title: str
    source_org: str
    superseded: bool = False  # from the document's status (ADR-0010)

    @property
    def section(self) -> str:
        return SECTION_SEPARATOR.join(self.section_path)

    @property
    def embed_text(self) -> str:
        """Text used for embeddings/BM25: a contextual header plus the body.

        Prefixing the title and section path lets short chunks match queries about
        their topic even when the body never repeats the topic words.
        """
        return f"{self.title}\n{self.section}\n{self.text}"

    def to_record(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "title": self.title,
            "source_org": self.source_org,
            "section_path": list(self.section_path),
            "section_slug": self.section_slug,
            "ordinal": self.ordinal,
            "token_count": self.token_count,
            "has_overlap": self.has_overlap,
            "superseded": self.superseded,
            "text": self.text,
        }

    @classmethod
    def from_record(cls, rec: dict[str, Any]) -> Chunk:
        return cls(
            chunk_id=rec["chunk_id"],
            doc_id=rec["doc_id"],
            title=rec["title"],
            source_org=rec["source_org"],
            section_path=tuple(rec["section_path"]),
            section_slug=rec["section_slug"],
            ordinal=rec["ordinal"],
            token_count=rec["token_count"],
            has_overlap=rec["has_overlap"],
            text=rec["text"],
            superseded=bool(rec.get("superseded", False)),
        )


# ------------------------------------------------------------- retrieval ----


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """One fused retrieval hit. Ranks are 1-based; None = not in that retriever's list."""

    chunk: Chunk
    rank: int
    score: float  # normalised fused score in (0, 1]
    dense_rank: int | None
    sparse_rank: int | None


@dataclass(frozen=True, slots=True)
class ExpandedQuery:
    original: str
    added_terms: tuple[str, ...]

    @property
    def text(self) -> str:
        """Query text used for retrieval: original plus deterministic expansions."""
        return " ".join((self.original, *self.added_terms)) if self.added_terms else self.original


# ------------------------------------------------------------ generation ----


@dataclass(frozen=True, slots=True)
class AnswerSentence:
    text: str  # as shown in the answer (table rows rendered "cell: cell")
    chunk_id: str
    start: int  # character span in the source chunk text (UI highlighting)
    end: int
    citation_id: int
    score: float


@dataclass(frozen=True, slots=True)
class CitedChunk:
    citation_id: int  # matches the [n] marker
    retrieved: RetrievedChunk
    spans: tuple[tuple[int, int], ...]  # sentence spans used from this chunk


@dataclass(frozen=True, slots=True)
class GeneratedAnswer:
    text: str  # answer with inline [n] markers; empty when nothing relevant was found
    sentences: tuple[AnswerSentence, ...]
    citations: tuple[CitedChunk, ...]

    @property
    def is_empty(self) -> bool:
        return not self.sentences


# ------------------------------------------------------------ validation ----


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Output of a Validator (ADR-0002). Implemented in Phase 3."""

    coverage: float
    query_support: float
    retrieval_score: float
    numeric_ok: bool
    confidence: float
