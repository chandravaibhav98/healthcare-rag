"""Test databases for Phase 5.

* SQLite: one migrated template file per session, copied per test (fast, isolated).
* PostgreSQL: `TEST_DATABASE_URL` if set (e.g. a local server), else a Testcontainers
  container when Docker is available, else the PostgreSQL variants are skipped. CI has
  Docker, so they always run there. SKIP_POSTGRES_TESTS=1 opts out locally. Each test gets an empty `public` schema + migrations.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.migrations import upgrade

PG_IMAGE = "postgres:17-alpine"


def sqlite_url(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


@pytest.fixture(scope="session")
def sqlite_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("db-template") / "template.db"
    upgrade(sqlite_url(path))
    return path


def _docker_available() -> bool:
    """Cheap check without opening a connection (docker-py leaks a socket on failure)."""
    if os.environ.get("DOCKER_HOST"):
        return True
    if os.name == "nt":
        return Path(r"\\.\pipe\docker_engine").exists()
    return Path("/var/run/docker.sock").exists()


@pytest.fixture(scope="session")
def postgres_server_url() -> Iterator[str]:
    if os.environ.get("SKIP_POSTGRES_TESTS") == "1":
        pytest.skip("SKIP_POSTGRES_TESTS=1")
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        yield url
        return
    if not _docker_available():
        pytest.skip("PostgreSQL tests need TEST_DATABASE_URL or a Docker daemon")
    # The suite turns warnings into errors. Ryuk (the reaper side-car) keeps a socket open
    # until interpreter exit, which would surface as an unclosed-socket error after the
    # run; the container is stopped explicitly below instead.
    os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")
    from testcontainers.community.postgres import PostgresContainer

    container = PostgresContainer(PG_IMAGE, driver="asyncpg")
    container.start()
    try:
        yield container.get_connection_url()
    finally:
        container.stop()
        container.get_docker_client().client.close()


async def _reset_schema(url: str) -> None:
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


def fresh_postgres(url: str) -> str:
    asyncio.run(_reset_schema(url))
    upgrade(url)
    return url


@pytest.fixture(params=["sqlite", "postgres"])
def database_url(request: pytest.FixtureRequest, tmp_path: Path) -> str:
    """A migrated, empty database. Tests using it run once per backend."""
    if request.param == "sqlite":
        path = tmp_path / "app.db"
        shutil.copyfile(request.getfixturevalue("sqlite_template"), path)
        return sqlite_url(path)
    return fresh_postgres(request.getfixturevalue("postgres_server_url"))


@pytest.fixture
def sqlite_database_url(sqlite_template: Path, tmp_path: Path) -> str:
    """SQLite only, for tests whose logic does not depend on the database engine."""
    path = tmp_path / "app.db"
    shutil.copyfile(sqlite_template, path)
    return sqlite_url(path)
