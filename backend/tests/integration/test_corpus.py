"""Guards on the committed synthetic corpus (plan §4 Phase 1, ADR-0001)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

from app.core.config import REPO_ROOT
from app.domain.models import DocStatus, Document, SourceOrg
from app.rag.ingestion.chunker import ChunkingConfig, chunk_document
from app.rag.ingestion.loader import load_corpus

pytestmark = pytest.mark.integration
CORPUS = REPO_ROOT / "corpus"
# Topics every organisation covers, so section-level relevance sets can reach >= 4 chunks.
CORE_TOPICS = {
    "hand-hygiene",
    "ppe",
    "transmission-based-precautions",
    "environmental-cleaning",
    "sterilization",
    "sharps-safety",
    "immunization-schedules",
    "cold-chain",
    "aefi-reporting",
    "outbreak-response",
    "waste-management",
    "device-associated-infections",
}


@pytest.fixture(scope="module")
def docs() -> list[Document]:
    return load_corpus(CORPUS)


def test_corpus_size_and_balance(docs: list[Document]) -> None:
    assert 40 <= len(docs) <= 60
    per_org = {org: sum(d.meta.source_org is org for d in docs) for org in SourceOrg}
    assert min(per_org.values()) >= 12, per_org


def test_core_topics_are_covered_by_every_organisation(docs: list[Document]) -> None:
    orgs_by_topic: dict[str, set[SourceOrg]] = defaultdict(set)
    for d in docs:
        if d.meta.status is DocStatus.CURRENT:
            for t in d.meta.topic:
                orgs_by_topic[t].add(d.meta.source_org)
    missing = {
        t: set(SourceOrg) - orgs_by_topic[t]
        for t in CORE_TOPICS
        if orgs_by_topic[t] != set(SourceOrg)
    }
    assert not missing, missing


def test_deliberate_conflicting_versions_exist(docs: list[Document]) -> None:
    pairs = {(d.meta.supersedes, d.doc_id) for d in docs if d.meta.supersedes}
    assert len(pairs) >= 3
    assert {o for o, _ in pairs} == {
        d.doc_id for d in docs if d.meta.status is DocStatus.SUPERSEDED
    }


def test_every_document_chunks_cleanly(docs: list[Document]) -> None:
    cfg = ChunkingConfig()
    ids: set[str] = set()
    for d in docs:
        chunks = chunk_document(d, cfg)
        assert len(chunks) >= 3, d.doc_id
        for c in chunks:
            assert c.chunk_id not in ids
            ids.add(c.chunk_id)
            assert c.token_count <= cfg.max_tokens * 1.2, c.chunk_id
            assert c.token_count >= 15, c.chunk_id


def test_corpus_files_are_lf_utf8_without_trailing_whitespace() -> None:
    for path in sorted(Path(CORPUS).rglob("*.md")):
        raw = path.read_bytes()
        assert b"\r" not in raw, path
        raw.decode("utf-8")
        assert all(line == line.rstrip() for line in raw.decode("utf-8").split("\n")), path
