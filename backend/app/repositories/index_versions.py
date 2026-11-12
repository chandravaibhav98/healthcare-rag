from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models import IndexVersion


async def get(session: AsyncSession, version: str) -> IndexVersion | None:
    return await session.get(IndexVersion, version)


async def register(
    session: AsyncSession, *, version: str, path: str, manifest: dict[str, Any], source: str
) -> IndexVersion:
    """Insert a version, or refresh the path of a known one (it may have moved)."""
    row = await get(session, version)
    if row is None:
        counts = manifest.get("counts", {})
        row = IndexVersion(
            version=version,
            path=path,
            manifest=manifest,
            source=source,
            document_count=int(counts.get("documents", 0)),
            chunk_count=int(counts.get("chunks", 0)),
            is_active=False,
        )
        session.add(row)
    else:
        row.path = path
    return row


async def all_versions(session: AsyncSession) -> Sequence[IndexVersion]:
    stmt = select(IndexVersion).order_by(IndexVersion.created_at.desc(), IndexVersion.version)
    return (await session.execute(stmt)).scalars().all()


async def active(session: AsyncSession) -> IndexVersion | None:
    stmt = select(IndexVersion).where(IndexVersion.is_active.is_(True)).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def set_active(session: AsyncSession, version: str) -> None:
    await session.execute(
        update(IndexVersion).where(IndexVersion.version != version).values(is_active=False)
    )
    await session.execute(
        update(IndexVersion)
        .where(IndexVersion.version == version)
        .values(is_active=True, activated_at=utcnow())
    )
