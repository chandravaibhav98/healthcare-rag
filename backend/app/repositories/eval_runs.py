from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvalRun
from app.repositories.paging import PageRequest, PageResult, paginate

SORTABLE = {"created_at": EvalRun.created_at}


def add(session: AsyncSession, *, split: str, triggered_by: uuid.UUID | None) -> EvalRun:
    run = EvalRun(split=split, status="queued", triggered_by=triggered_by)
    session.add(run)
    return run


async def get(session: AsyncSession, run_id: uuid.UUID) -> EvalRun | None:
    return await session.get(EvalRun, run_id)


async def active(session: AsyncSession) -> EvalRun | None:
    stmt = select(EvalRun).where(EvalRun.status.in_(("queued", "running"))).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def page(session: AsyncSession, status: str | None, req: PageRequest) -> PageResult[EvalRun]:
    stmt = select(EvalRun)
    if status:
        stmt = stmt.where(EvalRun.status == status)
    return await paginate(session, stmt, req, SORTABLE, "created_at", EvalRun.id)
