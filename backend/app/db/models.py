"""ORM models (plan §4 Phase 5 data model).

Portable across PostgreSQL (production) and SQLite (tests, local dev without Docker):
UUID primary keys via `sqlalchemy.Uuid`, JSON via `JSONType`, UTC timestamps via
`UTCDateTime`. Enumerated values are stored as short strings validated by the API layer
and a CHECK constraint, so adding a value is a migration, not a type change.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, UTCDateTime, utcnow


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('user', 'reviewer', 'admin')", name="role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class RefreshToken(Base):
    """One row per issued refresh token. Rotation links tokens of one login session
    (`family_id`); presenting a revoked token revokes the whole family (theft signal)."""

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    replaced_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class QueryLog(Base):
    """One answered `/qa` request. The question is stored only after PHI redaction
    (ADR-0009); `candidate_answer` is the withheld answer, for reviewers (ADR-0007)."""

    __tablename__ = "query_log"
    __table_args__ = (
        CheckConstraint("status IN ('validated', 'needs_review')", name="status"),
        Index("ix_query_log_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(Text)  # redacted
    redactions: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    signals: Mapped[dict[str, Any]] = mapped_column(JSONType)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    answer: Mapped[str] = mapped_column(Text)
    candidate_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    topics: Mapped[list[str]] = mapped_column(JSONType, default=list)
    top_k: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[float] = mapped_column(Float)
    index_version: Mapped[str] = mapped_column(String(32), index=True)
    # A user asked for a human to check this answer (Phase 6, "escalate for review").
    escalated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    escalation_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # redacted

    review: Mapped[Review | None] = relationship(back_populates="query", uselist=False)


class Review(Base):
    """A reviewer's verdict on one logged query (one per query; re-reviewing updates it).

    approve: the answer is correct and supported · reject: the guidelines do not answer
    it (the system should abstain) · correct: the reviewer names the chunks that do.
    `promote_to_gold` marks it for export into the gold dev set (closes the eval loop)."""

    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("verdict IN ('approve', 'reject', 'correct')", name="verdict"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    query_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("query_log.id", ondelete="CASCADE"), unique=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    verdict: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text, default="")
    corrected_citations: Mapped[list[str]] = mapped_column(JSONType, default=list)
    promote_to_gold: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    query: Mapped[QueryLog] = relationship(back_populates="review")


class EvalRun(Base):
    __tablename__ = "eval_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    split: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    index_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    scorecard: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class IndexVersion(Base):
    __tablename__ = "index_versions"

    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    path: Mapped[str] = mapped_column(String(1024))
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONType)
    document_count: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))  # boot | store | rebuild
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class AuditLog(Base):
    """Append-only record of security-relevant and configuration actions."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AppConfig(Base):
    """Versioned runtime tuning (threshold, floor, weights). Rows are never updated:
    each change inserts version + 1, so the history doubles as an audit trail."""

    __tablename__ = "app_config"

    version: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    values: Mapped[dict[str, Any]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    comment: Mapped[str] = mapped_column(String(500), default="")
