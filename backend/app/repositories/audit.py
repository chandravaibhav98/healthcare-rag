from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog
from app.repositories.paging import PageRequest, PageResult, paginate

SORTABLE = {"created_at": AuditLog.created_at}


@dataclass(frozen=True, slots=True)
class Actor:
    """Who did something. `None` fields mean the system (startup, purge job)."""

    id: uuid.UUID | None = None
    email: str | None = None
    request_id: str | None = None
    ip: str | None = None


SYSTEM = Actor(email="system")


def record(
    session: AsyncSession,
    actor: Actor,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor.id,
            actor_email=actor.email,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details or {},
            request_id=actor.request_id,
            ip=actor.ip,
        )
    )


@dataclass(frozen=True, slots=True)
class AuditFilter:
    action: str | None = None
    actor_email: str | None = None
    since: datetime | None = None
    until: datetime | None = None


async def page(session: AsyncSession, f: AuditFilter, req: PageRequest) -> PageResult[AuditLog]:
    stmt = select(AuditLog)
    if f.action:
        stmt = stmt.where(AuditLog.action.startswith(f.action))
    if f.actor_email:
        stmt = stmt.where(AuditLog.actor_email == f.actor_email.strip().lower())
    if f.since:
        stmt = stmt.where(AuditLog.created_at >= f.since)
    if f.until:
        stmt = stmt.where(AuditLog.created_at < f.until)
    return await paginate(session, stmt, req, SORTABLE, "created_at", AuditLog.id)
