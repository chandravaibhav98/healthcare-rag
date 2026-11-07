"""Phase 2 exit criterion: expected document in the top 5 for >= 9 of 10 smoke questions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.rag.pipeline import load_index
from app.rag.retrieval.hybrid import HybridRetriever
from app.rag.runtime import build_runtime

pytestmark = pytest.mark.integration
SMOKE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "smoke_questions.json").read_text("utf-8")
)


@pytest.fixture(scope="module")
def retriever(corpus_index_dir: Path) -> HybridRetriever:
    return build_runtime(load_index(corpus_index_dir), Settings(_env_file=None)).retriever


def test_smoke_set_hit_rate_at_5(retriever: HybridRetriever) -> None:
    questions = SMOKE["questions"]
    hits = [
        any(h.chunk.doc_id in q["expected"] for h in retriever.retrieve(q["q"], 5))
        for q in questions
    ]
    misses = [q["q"] for q, ok in zip(questions, hits, strict=True) if not ok]
    assert sum(hits) / len(hits) >= 0.9, f"misses: {misses}"


def test_fixture_corpus_question_finds_expected_doc(fixture_index_dir: Path) -> None:
    rt = build_runtime(load_index(fixture_index_dir), Settings(_env_file=None))
    hits = rt.retriever.retrieve("How often must hand hygiene compliance be monitored?", 5)
    assert "cdc-tst-002" in {h.chunk.doc_id for h in hits}


def test_end_to_end_answer_on_real_corpus(corpus_index_dir: Path) -> None:
    rt = build_runtime(load_index(corpus_index_dir), Settings(_env_file=None))
    q = "How often is respirator fit testing required?"
    answer = rt.generator.generate(q, rt.retriever.retrieve(q, 5))
    assert "annually" in answer.text
    assert all(not c.retrieved.chunk.superseded for c in answer.citations)
