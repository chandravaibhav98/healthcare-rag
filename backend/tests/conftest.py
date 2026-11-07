from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

FIXTURE_CORPUS = Path(__file__).parent / "fixtures" / "corpus"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
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
