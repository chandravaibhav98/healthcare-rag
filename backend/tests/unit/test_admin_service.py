"""Pure parts of the admin read models."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.admin_service import gold_candidate, percentile


@pytest.mark.parametrize(
    ("values", "q", "expected"),
    [
        ([], 0.5, None),
        ([7.0], 0.95, 7.0),
        ([1, 2, 3, 4], 0.5, 2.0),
        ([1, 2, 3, 4], 0.95, 4.0),
        (list(range(1, 101)), 0.95, 95.0),
    ],
)
def test_percentile_nearest_rank(values: list[float], q: float, expected: float | None) -> None:
    assert percentile(values, q) == expected


def _review(verdict: str, corrected: list[str]) -> Any:
    query = SimpleNamespace(
        id=uuid.uuid4(),
        question="When should gloves be worn?",
        topics=["ppe"],
        citations=[{"chunk_id": "who-tst-001::procedure::0001"}],
        index_version="abc123",
        redactions=0,
    )
    return SimpleNamespace(
        id=uuid.uuid4(), verdict=verdict, note="n", corrected_citations=corrected, query=query
    )


def test_gold_candidate_mapping() -> None:
    approved = gold_candidate(_review("approve", []))
    assert approved["g2"] == ["who-tst-001::procedure::0001"]
    assert approved["kind"] == "direct"
    assert approved["topic"] == "ppe"
    corrected = gold_candidate(_review("correct", ["cdc-tst-002::background::0001"]))
    assert corrected["g2"] == ["cdc-tst-002::background::0001"]
    rejected = gold_candidate(_review("reject", []))
    assert rejected["kind"] == "unanswerable"
    assert rejected["g2"] == []
    assert set(approved) == {"q", "kind", "g2", "g1", "kw", "topic", "source"}
