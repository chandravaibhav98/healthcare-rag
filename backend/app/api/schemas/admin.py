"""Admin API payloads (Phase 5). Every list endpoint returns the same `Page` envelope."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

QueryStatus = Literal["validated", "needs_review"]
Verdict = Literal["approve", "reject", "correct"]
EvalStatus = Literal["queued", "running", "succeeded", "failed"]


class Page[T](BaseModel):
    items: list[T]
    total: int = Field(description="Rows matching the filters (before limit/offset).")
    limit: int
    offset: int


# --- stats --------------------------------------------------------------------
class DailyPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    day: date
    total: int
    validated: int
    needs_review: int
    mean_confidence: float | None


class TopicCount(BaseModel):
    topic: str
    count: int


class StatsOut(BaseModel):
    since: datetime
    until: datetime
    total: int
    validated: int
    needs_review: int
    pass_rate: float | None = Field(description="validated / total (null when no queries).")
    abstention_rate: float | None
    mean_confidence: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    reasons: dict[str, int] = Field(description="Abstention reasons and counts.")
    top_topics: list[TopicCount]
    series: list[DailyPointOut] = Field(description="One point per UTC day with queries.")


# --- queries and reviews -----------------------------------------------------------
class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    query_id: uuid.UUID
    reviewer_id: uuid.UUID | None
    verdict: Verdict
    note: str
    corrected_citations: list[str]
    promote_to_gold: bool
    created_at: datetime
    updated_at: datetime


class QuerySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    request_id: str
    created_at: datetime
    user_id: uuid.UUID | None
    question: str = Field(description="Redacted before storage (ADR-0009).")
    redactions: int
    status: QueryStatus
    reason: str | None
    confidence: float
    top_k: int
    latency_ms: float
    index_version: str
    topics: list[str]
    reviewed: bool = False


class QueryDetail(QuerySummary):
    signals: dict[str, Any]
    citations: list[dict[str, Any]]
    answer: str
    candidate_answer: str | None = Field(
        description="Withheld low-confidence answer; visible to reviewers only (ADR-0007)."
    )
    review: ReviewOut | None


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Verdict
    note: str = Field(default="", max_length=4000)
    corrected_citations: list[str] = Field(
        default_factory=list, max_length=20, description="chunk_ids that answer the question."
    )
    promote_to_gold: bool = Field(
        default=False, description="Export this item as a gold dev-set candidate."
    )

    @model_validator(mode="after")
    def _correct_needs_citations(self) -> ReviewIn:
        if self.verdict == "correct" and not self.corrected_citations:
            raise ValueError("verdict 'correct' requires corrected_citations")
        return self


class ReviewQueueItem(BaseModel):
    """A row of the review queue: the query plus its review, if any."""

    query: QuerySummary
    review: ReviewOut | None


# --- evaluation runs -----------------------------------------------------------------
class EvalRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    split: str
    status: EvalStatus
    triggered_by: uuid.UUID | None
    index_version: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    scorecard: dict[str, Any] | None
    error: str | None


class EvalRunDetail(EvalRunOut):
    summary: dict[str, Any] | None


# --- index and corpus ------------------------------------------------------------------
class IndexVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    version: str
    path: str
    document_count: int
    chunk_count: int
    source: Literal["boot", "store", "rebuild"]
    is_active: bool
    created_at: datetime
    activated_at: datetime | None
    corpus_hash: str | None = None
    config_hash: str | None = None


class RebuildStatus(BaseModel):
    allowed: bool
    running: bool
    started_at: datetime | None
    finished_at: datetime | None
    last_version: str | None
    last_error: str | None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    doc_id: str
    title: str
    source_org: str
    version: str
    effective_date: str
    status: str
    supersedes: str | None
    topics: list[str]
    path: str
    chunk_count: int
    token_count: int


# --- runtime configuration -------------------------------------------------------------------
class WeightsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coverage: float = Field(ge=0.0, le=1.0)
    query_support: float = Field(ge=0.0, le=1.0)
    retrieval: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> WeightsModel:
        total = self.coverage + self.query_support + self.retrieval
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1.0, got {total:.4f}")
        return self


class ConfigValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold: float = Field(ge=0.0, le=1.0, description="Confidence threshold τ.")
    retrieval_floor: float = Field(ge=0.0, le=1.0)
    weights: WeightsModel


class ConfigOut(BaseModel):
    version: int = Field(description="0 = environment defaults (never changed at runtime).")
    values: ConfigValues
    updated_at: datetime | None
    updated_by: uuid.UUID | None
    comment: str | None


class ConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0, description="Version being edited (optimistic lock).")
    values: ConfigValues
    comment: str = Field(min_length=3, max_length=500, description="Why (kept in the audit log).")


# --- audit --------------------------------------------------------------------------------
class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    actor_id: uuid.UUID | None
    actor_email: str | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]
    request_id: str | None
    ip: str | None
