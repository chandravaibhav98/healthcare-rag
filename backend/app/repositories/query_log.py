from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import QueryLog, Review
from app.repositories.paging import PageRequest, PageResult, paginate

SORTABLE = {
    "created_at": QueryLog.created_at,
    "confidence": QueryLog.confidence,
    "latency_ms": QueryLog.latency_ms,
}


@dataclass(frozen=True, slots=True)
class QueryFilter:
    status: str | None = None
    reason: str | None = None
    min_confidence: float | None = None
    max_confidence: float | None = None
    since: datetime | None = None
    until: datetime | None = None
    index_version: str | None = None
    text: str | None = None
    reviewed: bool | None = None
    verdict: str | None = None
    promoted: bool | None = None
    #: Review queue "all": abstained OR reviewed (validated answers can be reviewed too).
    needs_review_or_reviewed: bool = False
    escalated: bool | None = None
    #: Review queue "pending": abstained OR escalated by a user, and not reviewed yet.
    awaiting_review: bool = False


def _apply(stmt: Select[Any], f: QueryFilter) -> Select[Any]:
    if f.status:
        stmt = stmt.where(QueryLog.status == f.status)
    if f.reason:
        stmt = stmt.where(QueryLog.reason == f.reason)
    if f.min_confidence is not None:
        stmt = stmt.where(QueryLog.confidence >= f.min_confidence)
    if f.max_confidence is not None:
        stmt = stmt.where(QueryLog.confidence <= f.max_confidence)
    if f.since:
        stmt = stmt.where(QueryLog.created_at >= f.since)
    if f.until:
        stmt = stmt.where(QueryLog.created_at < f.until)
    if f.index_version:
        stmt = stmt.where(QueryLog.index_version == f.index_version)
    if f.text:
        stmt = stmt.where(func.lower(QueryLog.question).contains(f.text.lower()))
    if f.reviewed is not None:
        has_review = select(Review.id).where(Review.query_id == QueryLog.id).exists()
        stmt = stmt.where(has_review if f.reviewed else ~has_review)
    if f.verdict:
        with_verdict = (
            select(Review.id)
            .where(Review.query_id == QueryLog.id, Review.verdict == f.verdict)
            .exists()
        )
        stmt = stmt.where(with_verdict)
    if f.needs_review_or_reviewed:
        any_review = select(Review.id).where(Review.query_id == QueryLog.id).exists()
        stmt = stmt.where(
            or_(QueryLog.status == "needs_review", QueryLog.escalated_at.is_not(None), any_review)
        )
    if f.escalated is not None:
        stmt = stmt.where(
            QueryLog.escalated_at.is_not(None) if f.escalated else QueryLog.escalated_at.is_(None)
        )
    if f.awaiting_review:
        any_review = select(Review.id).where(Review.query_id == QueryLog.id).exists()
        stmt = stmt.where(
            or_(QueryLog.status == "needs_review", QueryLog.escalated_at.is_not(None)), ~any_review
        )
    if f.promoted is not None:
        with_flag = (
            select(Review.id)
            .where(Review.query_id == QueryLog.id, Review.promote_to_gold.is_(f.promoted))
            .exists()
        )
        stmt = stmt.where(with_flag)
    return stmt


def add_many(session: AsyncSession, rows: Sequence[dict[str, Any]]) -> None:
    session.add_all(QueryLog(**row) for row in rows)


async def get(session: AsyncSession, query_id: uuid.UUID) -> QueryLog | None:
    stmt = select(QueryLog).where(QueryLog.id == query_id).options(selectinload(QueryLog.review))
    return (await session.execute(stmt)).scalar_one_or_none()


async def page(session: AsyncSession, f: QueryFilter, req: PageRequest) -> PageResult[QueryLog]:
    stmt = _apply(select(QueryLog).options(selectinload(QueryLog.review)), f)
    return await paginate(session, stmt, req, SORTABLE, "created_at", QueryLog.id)


async def window_rows(session: AsyncSession, since: datetime, until: datetime) -> Sequence[Any]:
    """Columns needed for dashboard statistics, for one time window."""
    stmt = select(
        QueryLog.created_at,
        QueryLog.status,
        QueryLog.reason,
        QueryLog.confidence,
        QueryLog.latency_ms,
        QueryLog.topics,
    ).where(QueryLog.created_at >= since, QueryLog.created_at < until)
    return (await session.execute(stmt)).all()


async def delete_older_than(session: AsyncSession, cutoff: datetime) -> int:
    result = await session.execute(delete(QueryLog).where(QueryLog.created_at < cutoff))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def get_by_request_id(session: AsyncSession, request_id: str) -> QueryLog | None:
    stmt = select(QueryLog).where(QueryLog.request_id == request_id).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()
