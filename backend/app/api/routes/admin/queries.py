"""Query explorer, review queue, reviews and the gold-set export (feedback loop)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse

from app.api.deps import ActorDep, RegistryDep, ReviewerDep, SessionDep, page_params
from app.api.routes.admin._common import PREFIX, responses, to_page
from app.api.schemas.admin import (
    Page,
    QueryDetail,
    QueryStatus,
    QuerySummary,
    ReviewIn,
    ReviewOut,
    ReviewQueueItem,
    Verdict,
)
from app.db.models import QueryLog
from app.repositories import audit
from app.repositories import query_log as query_repo
from app.repositories import reviews as review_repo
from app.repositories.paging import PageRequest
from app.services import admin_service

router = APIRouter(prefix=PREFIX, tags=["admin"])
NDJSON = "application/x-ndjson"


class NDJSONResponse(PlainTextResponse):
    media_type = NDJSON


QueryPage = Annotated[
    PageRequest, Depends(page_params(query_repo.SORTABLE, "created_at", name="QuerySort"))
]


def summary(row: QueryLog) -> QuerySummary:
    out = QuerySummary.model_validate(row)
    out.reviewed = row.review is not None
    return out


def detail(row: QueryLog) -> QueryDetail:
    return QueryDetail.model_validate(
        {
            **summary(row).model_dump(),
            "signals": row.signals,
            "citations": row.citations,
            "answer": row.answer,
            "candidate_answer": row.candidate_answer,
            "escalation_note": row.escalation_note,
            "review": ReviewOut.model_validate(row.review) if row.review else None,
        }
    )


@router.get(
    "/queries",
    response_model=Page[QuerySummary],
    operation_id="admin_list_queries",
    summary="Query explorer (filter, sort, paginate)",
    responses=responses(422),
)
async def list_queries(
    _: ReviewerDep,
    session: SessionDep,
    page: QueryPage,
    status_: Annotated[QueryStatus | None, Query(alias="status")] = None,
    reason: str | None = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    max_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
    index_version: str | None = None,
    q: Annotated[str | None, Query(max_length=200, description="Text in the question.")] = None,
    reviewed: bool | None = None,
    escalated: bool | None = None,
) -> Page[QuerySummary]:
    f = query_repo.QueryFilter(
        status=status_,
        reason=reason,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        since=since,
        until=until,
        index_version=index_version,
        text=q,
        reviewed=reviewed,
        escalated=escalated,
    )
    return to_page(await query_repo.page(session, f, page), summary)


@router.get(
    "/queries/{query_id}",
    response_model=QueryDetail,
    operation_id="admin_get_query",
    summary="One query with evidence, signals, withheld candidate answer and review",
    responses=responses(404, 422),
)
async def get_query(_: ReviewerDep, session: SessionDep, query_id: uuid.UUID) -> QueryDetail:
    row = await query_repo.get(session, query_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Query not found.")
    return detail(row)


@router.get(
    "/reviews",
    response_model=Page[ReviewQueueItem],
    operation_id="admin_list_reviews",
    summary="Review queue (pending) and review history (reviewed)",
    description="`pending`: abstained or user-escalated queries nobody has reviewed yet. "
    "`reviewed`: queries with a review (filter by `verdict`). `all`: every abstained, "
    "escalated or reviewed query.",
    responses=responses(422),
)
async def list_reviews(
    _: ReviewerDep,
    session: SessionDep,
    page: QueryPage,
    status_: Annotated[Literal["pending", "reviewed", "all"], Query(alias="status")] = "pending",
    verdict: Verdict | None = None,
    promoted: bool | None = None,
) -> Page[ReviewQueueItem]:
    if status_ == "pending":
        f = query_repo.QueryFilter(awaiting_review=True)
    elif status_ == "reviewed":
        f = query_repo.QueryFilter(reviewed=True, verdict=verdict, promoted=promoted)
    else:
        f = query_repo.QueryFilter(
            verdict=verdict, promoted=promoted, needs_review_or_reviewed=True
        )
    result = await query_repo.page(session, f, page)
    items = [
        ReviewQueueItem(
            query=summary(row),
            review=ReviewOut.model_validate(row.review) if row.review else None,
        )
        for row in result.items
    ]
    return Page(items=items, total=result.total, limit=result.limit, offset=result.offset)


@router.post(
    "/reviews/{query_id}",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="admin_review_query",
    summary="Approve, reject or correct a query (re-posting updates the review)",
    responses={**responses(404, 422), 200: {"model": ReviewOut, "description": "Updated"}},
)
async def review_query(
    reviewer: ReviewerDep,
    session: SessionDep,
    actor: ActorDep,
    registry: RegistryDep,
    response: Response,
    query_id: uuid.UUID,
    body: ReviewIn,
) -> ReviewOut:
    if await query_repo.get(session, query_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Query not found.")
    # Promoted corrections become gold labels: an unknown chunk_id would silently corrupt
    # the evaluation set (manual test F-10). The schema checks the format; this the existence.
    known = {c.chunk_id for c in registry.current().index.chunks}
    unknown = sorted(set(body.corrected_citations) - known)
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Unknown chunk_id(s) in the active index: {', '.join(unknown)}",
        )
    review, created = await review_repo.upsert(
        session,
        query_id=query_id,
        reviewer_id=reviewer.id,
        verdict=body.verdict,
        note=body.note,
        corrected_citations=body.corrected_citations,
        promote_to_gold=body.promote_to_gold,
    )
    await session.flush()
    audit.record(
        session,
        actor,
        "review.create" if created else "review.update",
        target_type="query",
        target_id=str(query_id),
        details={"verdict": body.verdict, "promote_to_gold": body.promote_to_gold},
    )
    await session.commit()
    await session.refresh(review)
    if not created:
        response.status_code = status.HTTP_200_OK
    return ReviewOut.model_validate(review)


@router.get(
    "/reviews/export/gold.jsonl",
    response_class=NDJSONResponse,
    operation_id="admin_export_gold_candidates",
    summary="Promoted reviews as gold dev-set candidates (JSONL)",
    description="One JSON object per line in the `gold_source.yaml` item format, plus a "
    "`source` block for traceability. Candidates need an annotator pass before they "
    "join the gold set (DATASET_CARD.md).",
    responses={**responses(), 200: {"content": {NDJSON: {"schema": {"type": "string"}}}}},
)
async def export_gold(_: ReviewerDep, session: SessionDep) -> NDJSONResponse:
    body = await admin_service.export_gold_jsonl(session)
    return NDJSONResponse(
        body,
        headers={"Content-Disposition": 'attachment; filename="gold_candidates.jsonl"'},
    )
