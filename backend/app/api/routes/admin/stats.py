"""Dashboard KPIs over a time window."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Final

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import ReviewerDep, SessionDep
from app.api.routes.admin._common import PREFIX, responses
from app.api.schemas.admin import DailyPointOut, StatsOut, TopicCount
from app.db.base import utcnow
from app.services import admin_service

router = APIRouter(prefix=PREFIX, tags=["admin"])
DEFAULT_WINDOW: Final = timedelta(days=7)
MAX_WINDOW: Final = timedelta(days=366)


def resolve_window(since: datetime | None, until: datetime | None) -> tuple[datetime, datetime]:
    for value in (since, until):
        if value is not None and value.tzinfo is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "from/to must include a timezone (e.g. 2026-11-01T00:00:00Z)",
            )
    end = until or utcnow()
    start = since or end - DEFAULT_WINDOW
    if start >= end:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "'from' must be before 'to'")
    if end - start > MAX_WINDOW:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "window is limited to 366 days")
    return start, end


@router.get(
    "/stats",
    response_model=StatsOut,
    operation_id="admin_stats",
    summary="Query volume, pass rate, confidence, latency and topics for a window",
    responses=responses(422),
)
async def get_stats(
    _: ReviewerDep,
    session: SessionDep,
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
) -> StatsOut:
    start, end = resolve_window(since, until)
    s = await admin_service.stats(session, start, end)
    return StatsOut(
        since=s.since,
        until=s.until,
        total=s.total,
        validated=s.validated,
        needs_review=s.needs_review,
        pass_rate=s.pass_rate,
        abstention_rate=s.abstention_rate,
        mean_confidence=s.mean_confidence,
        latency_p50_ms=s.latency_p50_ms,
        latency_p95_ms=s.latency_p95_ms,
        reasons=s.reasons,
        top_topics=[TopicCount(topic=t, count=c) for t, c in s.top_topics],
        series=[DailyPointOut.model_validate(p) for p in s.series],
    )
