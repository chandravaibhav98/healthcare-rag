from __future__ import annotations

import shutil
import threading
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import GeneratorKind, Settings
from app.rag.index.registry import IndexNotLoadedError, IndexRegistry
from app.rag.ingestion.chunker import ChunkingConfig
from app.rag.pipeline import BuildConfig, IndexIntegrityError, LoadedIndex, build_index
from app.rag.runtime import RagRuntime, build_runtime


def _registry() -> IndexRegistry:
    settings = Settings(_env_file=None)

    def factory(index: LoadedIndex) -> RagRuntime:
        return build_runtime(index, settings)

    return IndexRegistry(factory)


def test_not_loaded() -> None:
    reg = _registry()
    assert not reg.is_loaded
    with pytest.raises(IndexNotLoadedError):
        reg.current()


def test_load_and_atomic_swap(
    tmp_path: Path, fixture_index_dir: Path, fixture_corpus: Path
) -> None:
    reg = _registry()
    first = reg.load(fixture_index_dir)
    snapshot = reg.current()
    assert snapshot is first

    other = tmp_path / "other"
    build_index(
        fixture_corpus, other, BuildConfig(chunking=ChunkingConfig(min_tokens=50, max_tokens=100))
    )
    assert reg.reload_if_changed(other) is True
    assert reg.current().index_version != first.index_version
    # An in-flight request keeps a consistent view of the old index.
    assert snapshot.retriever.retrieve("gloves", 3)[0].chunk in snapshot.index.chunks
    assert reg.reload_if_changed(other) is False  # same version: no reload


def test_failed_load_keeps_previous_index(tmp_path: Path, fixture_index_dir: Path) -> None:
    reg = _registry()
    good = reg.load(fixture_index_dir)
    broken = tmp_path / "broken"
    shutil.copytree(fixture_index_dir, broken)
    (broken / "bm25.json").write_text("{}", encoding="utf-8")
    with pytest.raises(IndexIntegrityError):
        reg.load(broken)
    assert reg.current() is good


def test_concurrent_readers_during_swaps(fixture_index_dir: Path) -> None:
    reg = _registry()
    reg.load(fixture_index_dir)
    errors: list[BaseException] = []

    def reader() -> None:
        try:
            for _ in range(50):
                rt = reg.current()
                assert rt.retriever.retrieve("hand hygiene", 2)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for _ in range(5):
        reg.load(fixture_index_dir)
    for t in threads:
        t.join()
    assert not errors


def test_llm_generator_not_available(fixture_index_dir: Path) -> None:
    settings = Settings(
        _env_file=None,
        generator=GeneratorKind.LLM,
        openai_api_key=SecretStr("k"),
        openai_model="m",
    )
    from app.rag.pipeline import load_index

    with pytest.raises(NotImplementedError, match="extractive"):
        build_runtime(load_index(fixture_index_dir), settings)
