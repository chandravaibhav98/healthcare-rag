from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppConfig


async def latest(session: AsyncSession) -> AppConfig | None:
    stmt = select(AppConfig).order_by(AppConfig.version.desc()).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


def add(
    session: AsyncSession,
    *,
    version: int,
    values: dict[str, Any],
    created_by: uuid.UUID | None,
    comment: str,
) -> AppConfig:
    row = AppConfig(version=version, values=values, created_by=created_by, comment=comment)
    session.add(row)
    return row
