"""Offline index build: corpus/*.md → chunks → 256-D vectors → FAISS + BM25 + manifest.

Used by `backend/scripts/pipeline.py` (the spec's CLI) and, from Phase 8, by the index
image build. Every function here is deterministic for a given corpus and config.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from app.core.config import Settings
from app.domain.models import Chunk, Document
from app.rag.analysis import ANALYSIS_VERSION, analyze
from app.rag.embeddings import HashingEmbedder, HashingEmbedderConfig
from app.rag.index.bm25_store import BM25Index
from app.rag.index.faiss_store import FaissFlatIPStore
from app.rag.index.manifest import (
    MANIFEST_NAME,
    build_manifest,
    corpus_section,
    dump_json,
    read_manifest,
    verify_artifacts,
)
from app.rag.ingestion.chunker import ChunkingConfig, chunk_document
from app.rag.ingestion.loader import load_corpus

CHUNKS_FILE: Final = "chunks.jsonl"
FAISS_FILE: Final = "index.faiss"
BM25_FILE: Final = "bm25.json"
EMBEDDER_FILE: Final = "embedder.json"


class IndexIntegrityError(RuntimeError):
    """The on-disk index does not match its manifest (tampered, partial or stale)."""


@dataclass(frozen=True, slots=True)
class BuildConfig:
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embedder: HashingEmbedderConfig = field(default_factory=HashingEmbedderConfig)

    @classmethod
    def from_settings(cls, s: Settings) -> BuildConfig:
        return cls(
            chunking=ChunkingConfig(
                min_tokens=s.chunk_min_tokens,
                max_tokens=s.chunk_max_tokens,
                overlap_ratio=s.chunk_overlap_ratio,
            ),
            embedder=HashingEmbedderConfig(dim=s.embedding_dim, salt=s.embedding_hash_salt),
        )


@dataclass(frozen=True, slots=True)
class BuildResult:
    index_dir: Path
    manifest: dict[str, Any]
    documents: list[Document]
    chunks: list[Chunk]


def chunk_corpus(docs: list[Document], cfg: ChunkingConfig) -> list[Chunk]:
    chunks = [c for d in docs for c in chunk_document(d, cfg)]
    seen: set[str] = set()
    for c in chunks:
        if c.chunk_id in seen:
            raise ValueError(f"duplicate chunk id {c.chunk_id}")
        seen.add(c.chunk_id)
    return chunks


def build_artifacts(
    corpus_dir: Path, config: BuildConfig
) -> tuple[dict[str, bytes], dict[str, Any], list[Document], list[Chunk]]:
    """Pure build: returns artifact bytes and the manifest, writes nothing."""
    docs = load_corpus(corpus_dir)
    chunks = chunk_corpus(docs, config.chunking)
    texts = [c.embed_text for c in chunks]

    embedder = HashingEmbedder(config.embedder)
    embedder.fit(texts)
    store = FaissFlatIPStore(embedder.dim)
    store.add(embedder.embed(texts))

    bm25 = BM25Index()
    bm25.build([analyze(t) for t in texts])

    chunk_lines = "".join(
        json.dumps(c.to_record(), sort_keys=True, ensure_ascii=False) + "\n" for c in chunks
    )
    artifacts = {
        CHUNKS_FILE: chunk_lines.encode("utf-8"),
        FAISS_FILE: store.to_bytes(),
        BM25_FILE: bm25.to_bytes(),
        EMBEDDER_FILE: embedder.state_bytes(),
    }
    build_config = {
        "analysis_version": ANALYSIS_VERSION,
        "chunking": config.chunking.as_dict(),
        "embedder": embedder.config(),
        "bm25": bm25.config(),
    }
    manifest = build_manifest(docs, chunks, build_config, artifacts)
    return artifacts, manifest, docs, chunks


def build_index(corpus_dir: Path, out_dir: Path, config: BuildConfig | None = None) -> BuildResult:
    artifacts, manifest, docs, chunks = build_artifacts(corpus_dir, config or BuildConfig())
    _write_atomically(out_dir, {**artifacts, MANIFEST_NAME: dump_json(manifest)})
    return BuildResult(index_dir=out_dir, manifest=manifest, documents=docs, chunks=chunks)


def _write_atomically(out_dir: Path, files: dict[str, bytes]) -> None:
    """Readers never see a half-written index: write a sibling temp dir, then swap."""
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_dir.parent / f".{out_dir.name}.tmp-{os.getpid()}"
    old = out_dir.parent / f".{out_dir.name}.old-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    for name, data in files.items():
        (tmp / name).write_bytes(data)
    if out_dir.exists():
        out_dir.rename(old)
    tmp.rename(out_dir)
    shutil.rmtree(old, ignore_errors=True)


@dataclass(frozen=True, slots=True)
class LoadedIndex:
    manifest: dict[str, Any]
    chunks: list[Chunk]
    vectors: FaissFlatIPStore
    bm25: BM25Index
    embedder: HashingEmbedder

    @property
    def index_version(self) -> str:
        return str(self.manifest["index_version"])


def load_index(index_dir: Path) -> LoadedIndex:
    """Load an index after verifying every artifact against the manifest (fail fast)."""
    manifest = read_manifest(index_dir)
    problems = verify_artifacts(index_dir, manifest)
    if problems:
        raise IndexIntegrityError("; ".join(problems))
    chunks = [
        Chunk.from_record(json.loads(line))
        for line in (index_dir / CHUNKS_FILE).read_text(encoding="utf-8").splitlines()
        if line
    ]
    embedder = HashingEmbedder.from_state_bytes((index_dir / EMBEDDER_FILE).read_bytes())
    vectors = FaissFlatIPStore.from_bytes((index_dir / FAISS_FILE).read_bytes(), embedder.dim)
    bm25 = BM25Index.from_bytes((index_dir / BM25_FILE).read_bytes())
    if not (len(chunks) == vectors.size == bm25.size == manifest["counts"]["chunks"]):
        raise IndexIntegrityError("chunk, vector and BM25 counts disagree")
    return LoadedIndex(
        manifest=manifest, chunks=chunks, vectors=vectors, bm25=bm25, embedder=embedder
    )


def verify_index(index_dir: Path, corpus_dir: Path | None = None) -> list[str]:
    """Integrity problems, plus staleness against `corpus_dir` when one is given."""
    try:
        manifest = read_manifest(index_dir)
    except (FileNotFoundError, ValueError) as exc:
        return [str(exc)]
    problems = verify_artifacts(index_dir, manifest)
    if corpus_dir is not None:
        current = corpus_section(load_corpus(corpus_dir))["hash"]
        if current != manifest["corpus"]["hash"]:
            problems.append("index is stale: corpus changed since it was built (rebuild it)")
    return problems
