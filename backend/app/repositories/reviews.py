from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import utcnow
from app.db.models import QueryLog, Review
from app.repositories.paging import PageRequest, PageResult, paginate

SORTABLE = {"created_at": Review.created_at, "updated_at": Review.updated_at}


async def get_for_query(session: AsyncSession, query_id: uuid.UUID) -> Review | None:
    stmt = select(Review).where(Review.query_id == query_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert(
    session: AsyncSession,
    *,
    query_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    verdict: str,
    note: str,
    corrected_citations: list[str],
    promote_to_gold: bool,
) -> tuple[Review, bool]:
    """Create the review or overwrite the existing one. Returns (review, created)."""
    review = await get_for_query(session, query_id)
    created = review is None
    if review is None:
        review = Review(query_id=query_id)
        session.add(review)
    review.reviewer_id = reviewer_id
    review.verdict = verdict
    review.note = note
    review.corrected_citations = corrected_citations
    review.promote_to_gold = promote_to_gold
    review.updated_at = utcnow()
    return review, created


async def page(session: AsyncSession, verdict: str | None, req: PageRequest) -> PageResult[Review]:
    stmt = select(Review).options(selectinload(Review.query))
    if verdict:
        stmt = stmt.where(Review.verdict == verdict)
    return await paginate(session, stmt, req, SORTABLE, "updated_at", Review.id)


async def promoted(session: AsyncSession) -> Sequence[Review]:
    stmt = (
        select(Review)
        .join(QueryLog, QueryLog.id == Review.query_id)
        .where(Review.promote_to_gold.is_(True))
        .options(selectinload(Review.query))
        .order_by(Review.updated_at, Review.id)
    )
    return (await session.execute(stmt)).scalars().all()
