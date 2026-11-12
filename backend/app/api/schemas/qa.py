"""API contract v1: ``POST /api/v1/qa`` (canonical) and ``POST /qa`` (alias from the brief).

Contract rules (ADR-0006):
* The brief's four fields (``answer``, ``citations``, ``confidence``, ``status``) are
  top-level, exactly named and always present. They are never renamed or removed in v1.
* Everything else is additive and lives in the optional ``meta`` object.

The invariants enforced below are the ones a client must be able to rely on. Encoding
them in the schema means Phase 3 cannot ship a response that breaks them.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Final, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.domain.ids import CHUNK_ID_PATTERN, DOC_ID_PATTERN, INDEX_VERSION_PATTERN

CONTRACT_VERSION: Final = "1.1.0"  # 1.1: additive Citation.superseded (ADR-0006, ADR-0010)

#: Fixed answer text when abstaining (ADR-0007). Clients may rely on it verbatim.
ABSTENTION_MESSAGE: Final = (
    "The indexed guidelines do not contain sufficient evidence to answer this confidently. "
    "Please consult the cited sources or escalate for review."
)

QUESTION_MIN_LEN: Final = 3
QUESTION_MAX_LEN: Final = 1000
TOP_K_MIN: Final = 1
TOP_K_MAX: Final = 20
TOP_K_DEFAULT: Final = 5

#: Inline citation marker in an answer, e.g. "... before donning gloves [1]."
CITATION_MARKER_RE: Final = re.compile(r"\[(\d+)\]")

Question = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=QUESTION_MIN_LEN, max_length=QUESTION_MAX_LEN
    ),
]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]


class QAStatus(StrEnum):
    VALIDATED = "validated"
    NEEDS_REVIEW = "needs_review"


class AbstentionReason(StrEnum):
    """Why an answer was withheld (ADR-0007). Ordered from most to least specific."""

    NO_EVIDENCE = "no_evidence"
    BELOW_RETRIEVAL_FLOOR = "below_retrieval_floor"
    NUMERIC_MISMATCH = "numeric_mismatch"
    LOW_CONFIDENCE = "low_confidence"


class QARequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"question": "When should health workers perform hand hygiene?", "top_k": 5}
            ]
        },
    )

    question: Question = Field(
        description="Natural-language question about the indexed guidelines."
    )
    top_k: int = Field(
        default=TOP_K_DEFAULT,
        ge=TOP_K_MIN,
        le=TOP_K_MAX,
        description="Number of evidence chunks to retrieve.",
    )


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(ge=1, description="Matches the inline [n] marker in `answer`.")
    doc_id: str = Field(pattern=DOC_ID_PATTERN, examples=["who-ipc-004"])
    title: str = Field(min_length=1)
    source_org: str = Field(min_length=1, examples=["WHO", "NIH", "CDC"])
    section_path: str = Field(min_length=1, examples=["PPE › Gloves"])
    chunk_id: str = Field(pattern=CHUNK_ID_PATTERN, examples=["who-ipc-004::ppe-gloves::0002"])
    snippet: str = Field(
        min_length=1, max_length=2000, description="Evidence text shown to the user."
    )
    score: UnitFloat = Field(description="Normalised retrieval score of this chunk.")
    superseded: bool = Field(
        default=False,
        description="The source document has been replaced by a newer version (ADR-0010).",
    )


class Signals(BaseModel):
    """The components of `confidence` (ADR-0002), exposed for transparency."""

    model_config = ConfigDict(extra="forbid")

    coverage: UnitFloat = Field(
        description="Share of answer content tokens found in the cited evidence."
    )
    query_support: UnitFloat = Field(
        description="Share of question key terms found in the cited evidence."
    )
    retrieval_score: UnitFloat = Field(
        description="Normalised fused retrieval score of the cited chunks."
    )
    numeric_ok: bool = Field(
        description="Every number/unit in the answer appears in its cited evidence."
    )


class ResponseMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    index_version: str = Field(pattern=INDEX_VERSION_PATTERN)
    latency_ms: float = Field(ge=0.0)
    abstained: bool
    reason: AbstentionReason | None = None
    signals: Signals

    @model_validator(mode="after")
    def _reason_iff_abstained(self) -> Self:
        if self.abstained != (self.reason is not None):
            raise ValueError("`reason` must be set if and only if `abstained` is true")
        return self


class QAResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "answer": "Perform hand hygiene before donning gloves and after removing them [1].",
                    "citations": [
                        {
                            "id": 1,
                            "doc_id": "who-ipc-004",
                            "title": "Glove Use in Health Care (synthetic)",
                            "source_org": "WHO",
                            "section_path": "PPE › Gloves",
                            "chunk_id": "who-ipc-004::ppe-gloves::0002",
                            "snippet": "Hand hygiene must be performed before donning gloves ...",
                            "score": 0.82,
                        }
                    ],
                    "confidence": 0.78,
                    "status": "validated",
                    "meta": {
                        "request_id": "01JC9Z6X4Q2V8M3T5N7R1K0B2D",
                        "index_version": "a1b2c3d",
                        "latency_ms": 41.0,
                        "abstained": False,
                        "signals": {
                            "coverage": 1.0,
                            "query_support": 0.71,
                            "retrieval_score": 0.64,
                            "numeric_ok": True,
                        },
                    },
                }
            ]
        },
    )

    answer: str = Field(
        min_length=1, description="Extractive answer with [n] markers, or the abstention message."
    )
    citations: list[Citation] = Field(
        description="Evidence; present even when abstaining (ADR-0007)."
    )
    confidence: UnitFloat = Field(description="Composite support score (ADR-0002).")
    status: QAStatus = Field(
        description="`validated` only when confidence ≥ threshold and numeric_ok."
    )
    meta: ResponseMeta | None = Field(default=None, description="Additive diagnostics (ADR-0006).")

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        ids = [c.id for c in self.citations]
        if ids != list(range(1, len(ids) + 1)):
            raise ValueError("citation ids must be 1..n in order")

        markers = {int(m) for m in CITATION_MARKER_RE.findall(self.answer)}
        unknown = markers - set(ids)
        if unknown:
            raise ValueError(f"answer references unknown citation ids: {sorted(unknown)}")

        if self.status is QAStatus.VALIDATED and not self.citations:
            raise ValueError("a validated answer must cite at least one source")

        if self.meta is not None:
            if self.meta.abstained != (self.status is QAStatus.NEEDS_REVIEW):
                raise ValueError("meta.abstained must be true exactly when status is needs_review")
            if self.status is QAStatus.VALIDATED and not self.meta.signals.numeric_ok:
                raise ValueError("a validated answer must pass the numeric consistency gate")
        return self
