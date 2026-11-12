"""The committed gold files are current, consistent with the index, and leak-free."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from evaluation import build_gold
from evaluation.schemas import Split, load_gold_jsonl

pytestmark = pytest.mark.integration


def test_gold_files_are_current(corpus_index_dir: Path) -> None:
    assert build_gold.main(["--index", str(corpus_index_dir), "--check"]) == 0


def test_manifest_pins_the_index_and_both_sources(corpus_index_dir: Path) -> None:
    meta = json.loads(build_gold.MANIFEST_PATH.read_text(encoding="utf-8"))
    built = json.loads((corpus_index_dir / "manifest.json").read_text(encoding="utf-8"))
    assert meta["index_version"] == built["index_version"]
    for path in (build_gold.SOURCE, build_gold.TEST_SOURCE):
        assert meta["source_sha256"][path.name] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_dev_and_test_do_not_overlap() -> None:
    dev = load_gold_jsonl(build_gold.DEV_PATH)
    test = load_gold_jsonl(build_gold.TEST_PATH)
    assert {g.split for g in dev} == {Split.DEV}
    assert {g.split for g in test} == {Split.TEST}
    assert not {g.question.lower() for g in dev} & {g.question.lower() for g in test}
    assert not {g.id for g in dev} & {g.id for g in test}


def test_both_splits_test_abstention() -> None:
    for path in (build_gold.DEV_PATH, build_gold.TEST_PATH):
        items = load_gold_jsonl(path)
        share = sum(not g.answerable for g in items) / len(items)
        assert 0.10 <= share <= 0.20, (path.name, share)
