from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


def normalise_email(email: str) -> str:
    return email.strip().lower()


async def get(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == normalise_email(email))
    return (await session.execute(stmt)).scalar_one_or_none()


def add(
    session: AsyncSession, *, email: str, display_name: str, password_hash: str, role: str
) -> User:
    user = User(
        email=normalise_email(email),
        display_name=display_name,
        password_hash=password_hash,
        role=role,
    )
    session.add(user)
    return user


async def count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(User))).scalar_one())
