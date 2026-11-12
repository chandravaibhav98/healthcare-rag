from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.rag.index.registry import IndexRegistry
from app.rag.runtime import build_runtime
from tests.support import AuthedClient

# Database fixtures (SQLite template, PostgreSQL via TEST_DATABASE_URL or Testcontainers).
pytest_plugins = ["tests.persistence"]

FIXTURE_CORPUS = Path(__file__).parent / "fixtures" / "corpus"

AppFactory = Callable[..., FastAPI]


def make_settings(**overrides: Any) -> Settings:
    """Test settings: no .env, deterministic defaults, generous rate limit, and no
    database unless a test asks for one (a developer's exported DATABASE_URL must not leak
    into stateless tests)."""
    base: dict[str, Any] = {
        "rate_limit_qa": "10000/minute",
        "log_format": "console",
        "database_url": "",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def make_registry(index_dir: Path, settings: Settings) -> IndexRegistry:
    registry = IndexRegistry(lambda index: build_runtime(index, settings))
    registry.load(index_dir)
    return registry


@pytest.fixture
def app_factory(fixture_index_dir: Path) -> AppFactory:
    """`app_factory(preload=True, **settings_overrides)` → app on the fixture index.

    With `preload=False` the registry starts empty, so the lifespan has to load the
    index (or fail fast); without entering the lifespan it stays unloaded.
    """

    def factory(*, preload: bool = True, **overrides: Any) -> FastAPI:
        overrides.setdefault("index_dir", fixture_index_dir)
        settings = make_settings(**overrides)
        registry = make_registry(settings.index_dir, settings) if preload else None
        return create_app(settings, registry)

    return factory


@pytest.fixture
def fixture_registry(fixture_index_dir: Path) -> IndexRegistry:
    return make_registry(fixture_index_dir, make_settings())


@pytest.fixture
def client(app_factory: AppFactory) -> Iterator[TestClient]:
    """App wired to the two-document fixture index (fast, fully controlled)."""
    with TestClient(app_factory()) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def corpus_client(corpus_index_dir: Path) -> Iterator[TestClient]:
    """App wired to the real synthetic corpus (behavioural checks)."""
    settings = make_settings(index_dir=corpus_index_dir)
    app = create_app(settings, make_registry(corpus_index_dir, settings))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def fixture_corpus() -> Path:
    return FIXTURE_CORPUS


@pytest.fixture(scope="session")
def fixture_index_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from app.rag.ingestion.chunker import ChunkingConfig
    from app.rag.pipeline import BuildConfig, build_index

    out = tmp_path_factory.mktemp("fixture-index") / "index"
    build_index(
        FIXTURE_CORPUS, out, BuildConfig(chunking=ChunkingConfig(min_tokens=60, max_tokens=120))
    )
    return out


@pytest.fixture(scope="session")
def corpus_index_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The real corpus, built once per test session (about 1 s)."""
    from app.core.config import REPO_ROOT
    from app.rag.pipeline import build_index

    out = tmp_path_factory.mktemp("corpus-index") / "index"
    build_index(REPO_ROOT / "corpus", out)
    return out


# --- Phase 5: persistence, users and authenticated clients ---------------------------------


@pytest.fixture(autouse=True, scope="session")
def _fast_password_hashing() -> Iterator[None]:
    """Argon2 at minimum cost in tests: the production parameters cost ~50 ms per hash on
    purpose, which would dominate the suite (every API test logs in three personas). The
    algorithm (argon2id) and the code paths are unchanged; only the cost parameters drop."""
    from argon2 import PasswordHasher

    from app.core import security

    original = security._hasher
    security._hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    yield
    security._hasher = original


@pytest.fixture
def db_app_factory(
    app_factory: AppFactory, tmp_path: Path, fixture_corpus: Path
) -> Callable[..., FastAPI]:
    def factory(url: str, **overrides: Any) -> FastAPI:
        overrides.setdefault("index_store_dir", tmp_path / "indexes")
        overrides.setdefault("corpus_dir", fixture_corpus)
        overrides.setdefault("login_rate_limit", "10000/minute")
        return app_factory(database_url=url, **overrides)

    return factory


@pytest.fixture
def api(db_app_factory: Callable[..., FastAPI], database_url: str) -> Iterator[AuthedClient]:
    """App with a database (SQLite and PostgreSQL) plus one account per role."""
    with TestClient(db_app_factory(database_url)) as client:
        yield AuthedClient.create(client)


@pytest.fixture
def lite_api(
    db_app_factory: Callable[..., FastAPI], sqlite_database_url: str
) -> Iterator[AuthedClient]:
    """Same as `api`, SQLite only (engine-independent behaviour, e.g. the RBAC matrix)."""
    with TestClient(db_app_factory(sqlite_database_url)) as client:
        yield AuthedClient.create(client)
