"""Alembic migrations: upgrade/downgrade round trip and no drift between models and DDL
(both SQLite and PostgreSQL)."""

from __future__ import annotations

import asyncio

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base
from app.db.migrations import alembic_config, head_revision
from app.db.session import Database


async def _diff(url: str) -> list[object]:
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        diff = await conn.run_sync(
            lambda sync: compare_metadata(
                MigrationContext.configure(sync, opts={"compare_type": True}), Base.metadata
            )
        )
    await engine.dispose()
    return list(diff)


async def _revision(url: str) -> str | None:
    db = Database(url)
    try:
        return await db.schema_revision()
    finally:
        await db.dispose()


def _cfg(url: str):  # type: ignore[no-untyped-def]
    from app.db.migrations import _XArgs

    cfg = alembic_config()
    cfg.cmd_opts = _XArgs(url)  # type: ignore[assignment]
    return cfg


def test_schema_matches_models(database_url: str) -> None:
    assert asyncio.run(_revision(database_url)) == head_revision()
    assert asyncio.run(_diff(database_url)) == []


def test_downgrade_and_upgrade_round_trip(database_url: str) -> None:
    command.downgrade(_cfg(database_url), "base")
    assert asyncio.run(_revision(database_url)) is None
    command.upgrade(_cfg(database_url), "head")
    assert asyncio.run(_revision(database_url)) == head_revision()
    assert asyncio.run(_diff(database_url)) == []


def test_api_refuses_an_unmigrated_database(tmp_path, app_factory) -> None:  # type: ignore[no-untyped-def]
    import pytest
    from fastapi.testclient import TestClient

    from app.db.migrations import SchemaNotAtHeadError

    url = f"sqlite+aiosqlite:///{(tmp_path / 'empty.db').as_posix()}"
    with (
        pytest.raises(SchemaNotAtHeadError, match="db-migrate"),
        TestClient(app_factory(database_url=url)),
    ):
        pass
