"""Engine and session factory. One `Database` per app instance, created in the lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = make_url(url)
        self.is_sqlite = self.url.get_backend_name() == "sqlite"
        kwargs: dict[str, object] = {"echo": echo}
        if not self.is_sqlite:
            kwargs.update(pool_pre_ping=True, pool_size=5, max_overflow=10, pool_recycle=1800)
        self.engine: AsyncEngine = create_async_engine(url, **kwargs)
        if self.is_sqlite:
            # SQLite ignores foreign keys unless asked, which would hide cascade bugs.
            @event.listens_for(self.engine.sync_engine, "connect")
            def _fk_on(dbapi_conn, _record):  # type: ignore[no-untyped-def]
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            yield session

    async def ping(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    async def schema_revision(self) -> str | None:
        """Current Alembic revision, or None if migrations never ran."""
        try:
            async with self.engine.connect() as conn:
                row = (await conn.execute(text("SELECT version_num FROM alembic_version"))).first()
        except Exception:
            return None
        return str(row[0]) if row else None

    async def dispose(self) -> None:
        await self.engine.dispose()
