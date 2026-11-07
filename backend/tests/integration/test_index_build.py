"""End-to-end index build on the fixture corpus: determinism and integrity (SC1)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.rag.analysis import analyze
from app.rag.index.manifest import MANIFEST_NAME
from app.rag.ingestion.chunker import ChunkingConfig
from app.rag.pipeline import BuildConfig, IndexIntegrityError, build_index, load_index, verify_index

pytestmark = pytest.mark.integration
SMALL = BuildConfig(chunking=ChunkingConfig(min_tokens=60, max_tokens=120))


def _files(d: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(d.iterdir())}


def test_two_builds_are_byte_identical(tmp_path: Path, fixture_corpus: Path) -> None:
    a = build_index(fixture_corpus, tmp_path / "a", SMALL)
    b = build_index(fixture_corpus, tmp_path / "b", SMALL)
    assert _files(tmp_path / "a") == _files(tmp_path / "b")
    assert a.manifest["index_version"] == b.manifest["index_version"]
    assert set(_files(tmp_path / "a")) == {
        "bm25.json",
        "chunks.jsonl",
        "embedder.json",
        "index.faiss",
        MANIFEST_NAME,
    }


def test_crlf_corpus_produces_the_same_index(tmp_path: Path, fixture_corpus: Path) -> None:
    crlf = tmp_path / "crlf"
    shutil.copytree(fixture_corpus, crlf)
    for p in crlf.rglob("*.md"):
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
    build_index(fixture_corpus, tmp_path / "lf-idx", SMALL)
    build_index(crlf, tmp_path / "crlf-idx", SMALL)
    assert _files(tmp_path / "lf-idx") == _files(tmp_path / "crlf-idx")


def test_corpus_or_config_change_changes_index_version(
    tmp_path: Path, fixture_corpus: Path
) -> None:
    base = build_index(fixture_corpus, tmp_path / "base", SMALL).manifest["index_version"]
    changed_cfg = BuildConfig(chunking=ChunkingConfig(min_tokens=60, max_tokens=130))
    assert (
        build_index(fixture_corpus, tmp_path / "cfg", changed_cfg).manifest["index_version"] != base
    )
    edited = tmp_path / "edited"
    shutil.copytree(fixture_corpus, edited)
    doc = edited / "who" / "who-tst-001.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nOne more sentence.\n", encoding="utf-8")
    assert build_index(edited, tmp_path / "e", SMALL).manifest["index_version"] != base


def test_manifest_has_no_host_specific_data(tmp_path: Path, fixture_corpus: Path) -> None:
    m = build_index(fixture_corpus, tmp_path / "i", SMALL).manifest
    text = json.dumps(m)
    assert str(tmp_path) not in text
    assert str(fixture_corpus) not in text
    assert m["environment"]["python"].count(".") == 1  # minor version only
    assert len(m["index_version"]) == 12


def test_load_index_roundtrip_and_hybrid_signals(tmp_path: Path, fixture_corpus: Path) -> None:
    built = build_index(fixture_corpus, tmp_path / "i", SMALL)
    idx = load_index(tmp_path / "i")
    assert [c.chunk_id for c in idx.chunks] == [c.chunk_id for c in built.chunks]
    q = "how often is hand hygiene compliance monitored"
    dense = idx.vectors.search(idx.embedder.embed([q]), 3)[0]
    sparse = idx.bm25.search(analyze(q), 3)
    top_ids = {idx.chunks[i].doc_id for i, _ in dense[:2]} | {
        idx.chunks[i].doc_id for i, _ in sparse[:2]
    }
    assert "cdc-tst-002" in top_ids


def test_tampering_and_staleness_are_detected(tmp_path: Path, fixture_corpus: Path) -> None:
    corpus = tmp_path / "c"
    shutil.copytree(fixture_corpus, corpus)
    build_index(corpus, tmp_path / "i", SMALL)
    assert verify_index(tmp_path / "i", corpus) == []

    doc = corpus / "cdc" / "cdc-tst-002.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nNew text.\n", encoding="utf-8")
    assert any("stale" in p for p in verify_index(tmp_path / "i", corpus))

    faiss_file = tmp_path / "i" / "index.faiss"
    faiss_file.write_bytes(faiss_file.read_bytes()[:-1] + b"\x00")
    assert any("index.faiss" in p for p in verify_index(tmp_path / "i"))
    with pytest.raises(IndexIntegrityError):
        load_index(tmp_path / "i")


def test_missing_index_is_reported(tmp_path: Path) -> None:
    assert "build the index first" in verify_index(tmp_path / "nope")[0]
