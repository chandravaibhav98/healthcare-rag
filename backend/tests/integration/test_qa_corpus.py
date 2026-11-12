"""End-to-end `/qa` behaviour on the real synthetic corpus.

Not the evaluation gate (that is Phase 4 on the annotated test split). This guards
against regressions: the Phase 2 smoke questions must validate and clearly off-topic
questions must abstain.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SMOKE = json.loads((Path(__file__).parents[1] / "fixtures" / "smoke_questions.json").read_text())
OFF_TOPIC = [
    "What is the capital of France?",
    "Who won the football world cup?",
    "How long should I boil an egg?",
    "How do I renew my passport?",
]


def test_smoke_questions_are_mostly_validated_with_expected_sources(
    corpus_client: TestClient,
) -> None:
    validated = cited_expected = 0
    for item in SMOKE["questions"]:
        body = corpus_client.post("/api/v1/qa", json={"question": item["q"]}).json()
        validated += body["status"] == "validated"
        cited_expected += any(c["doc_id"] in item["expected"] for c in body["citations"])
    n = len(SMOKE["questions"])
    assert validated >= 0.8 * n, f"{validated}/{n} validated"
    assert cited_expected >= 0.8 * n, f"{cited_expected}/{n} cite an expected document"


@pytest.mark.parametrize("question", OFF_TOPIC)
def test_off_topic_questions_abstain(corpus_client: TestClient, question: str) -> None:
    body = corpus_client.post("/qa", json={"question": question}).json()
    assert body["status"] == "needs_review"
    assert body["meta"]["abstained"]
