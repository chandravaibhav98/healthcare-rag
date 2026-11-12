from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.db.models import RefreshToken


def add(
    session: AsyncSession, *, jti: str, user_id: uuid.UUID, family_id: str, expires_at: datetime
) -> None:
    session.add(RefreshToken(jti=jti, user_id=user_id, family_id=family_id, expires_at=expires_at))


async def get(session: AsyncSession, jti: str) -> RefreshToken | None:
    return await session.get(RefreshToken, jti)


async def revoke_family(session: AsyncSession, family_id: str) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


async def delete_expired(session: AsyncSession, now: datetime) -> int:
    result = await session.execute(delete(RefreshToken).where(RefreshToken.expires_at < now))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def active_family_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = (
        select(RefreshToken.family_id)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .distinct()
    )
    return len((await session.execute(stmt)).all())
