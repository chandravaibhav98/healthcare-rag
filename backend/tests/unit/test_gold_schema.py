from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from evaluation.schemas import (
    GoldDatasetError,
    GoldItem,
    QuestionKind,
    load_gold_jsonl,
    parse_gold_lines,
)

DATASETS = Path(__file__).resolve().parents[2] / "evaluation" / "datasets"
A = "who-ipc-004::ppe-gloves::0002"
B = "who-ipc-004::ppe-gloves::0003"


def _item(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "q-0001",
        "question": "When should hand hygiene be performed?",
        "split": "dev",
        "topic": "hand-hygiene",
        "kind": "direct",
        "answerable": True,
        "relevant_chunk_ids": [A, B],
        "grades": {A: 2, B: 1},
        "expected_keywords": ["before donning"],
    }
    return {**base, **overrides}


def test_example_dataset_is_valid_and_covers_every_kind_of_case() -> None:
    items = load_gold_jsonl(DATASETS / "gold_example.jsonl")
    assert len(items) == 3
    assert any(not i.answerable for i in items)
    assert {i.kind for i in items} >= {QuestionKind.DIRECT, QuestionKind.UNANSWERABLE}


def test_valid_unanswerable_item() -> None:
    item = GoldItem.model_validate(
        _item(
            answerable=False,
            kind="unanswerable",
            relevant_chunk_ids=[],
            grades={},
            expected_keywords=[],
        )
    )
    assert not item.relevant_chunk_ids


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"grades": {A: 2}}, "one entry per relevant chunk"),
        ({"relevant_chunk_ids": [A, A], "grades": {A: 2}}, "unique"),
        ({"grades": {A: 1, B: 1}}, "grade 2"),
        ({"grades": {A: 3, B: 1}}, "Input should be 1 or 2"),
        ({"kind": "unanswerable"}, "contradicts"),
        ({"answerable": False}, "requires kind=unanswerable"),
        ({"answerable": False, "kind": "unanswerable"}, "must not list relevant chunks"),
        ({"relevant_chunk_ids": ["not-a-chunk"], "grades": {"not-a-chunk": 2}}, "pattern"),
        ({"id": "Q1"}, "pattern"),
        ({"split": "train"}, "'dev' or 'test'"),
    ],
)
def test_invalid_items_are_rejected(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        GoldItem.model_validate(_item(**overrides))


def test_duplicate_ids_report_the_line_number() -> None:
    line = json.dumps(_item())
    with pytest.raises(GoldDatasetError, match=r"<memory>:2: duplicate id q-0001"):
        parse_gold_lines([line, line])


def test_malformed_json_reports_the_line_number() -> None:
    with pytest.raises(GoldDatasetError, match=r"<memory>:1:"):
        parse_gold_lines(["{not json"])
