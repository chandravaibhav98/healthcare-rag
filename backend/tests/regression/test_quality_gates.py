"""Evaluation regression tests: the SC2/SC3 gates as part of `pytest` (plan Phase 7).

`scripts/eval.sh --gate` already guards the dev pool in CI; these tests put the same
gates into the ordinary test run, so a retrieval or validation change that lowers quality
fails `scripts/test.sh` locally too, before a pull request is opened.

What is enforced, and why (docs/evaluation-report.md, ADR-0001/0002):

* **Dev pool, no regression**: every scorecard metric at or above `baseline.json`
  (within the evaluator's tolerance) and no new false validations.
* **SC3** (pass rate at τ = 0.6 ≥ 0.80) on the dev pool and the held-out test split.
* **SC2** in its ceiling-normalised reading: literal P@5 cannot reach 0.65 on this corpus
  (most questions have fewer than five relevant chunks, report §3.1), so the gate is P@5 as
  a share of the best possible P@5, which has been stable at 0.72-0.73. The literal value is
  still reported by `scripts/eval.sh` and awaits the mentor decision in the plan.
* **Held-out test split, frozen snapshot**: the test split is never used for tuning; here it
  is only *observed*, and must not get worse than the record below. Its false-validation
  rate is above the 5 % target (open item OI-27), so that metric is pinned at its recorded
  value: any increase fails, and fixing OI-27 means lowering the pin.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

import pytest

from app.core.config import Settings
from app.rag.pipeline import load_index
from evaluation.common import check_index
from evaluation.run import (
    BASELINE_PATH,
    MAX_FALSE_VALIDATION,
    SC3_PASS_RATE,
    TOLERANCE,
    check_gate,
    evaluate_split,
)
from evaluation.schemas import Split

pytestmark = pytest.mark.integration

# P@5 / best possible P@5: the ceiling-normalised SC2 reading (report §3.1).
MIN_P5_OF_CEILING: Final = 0.70

# Frozen held-out record (docs/evaluation-report.md). Update only with a report change.
TEST_SPLIT_RECORD: Final[dict[str, float]] = {
    "pass_rate": 0.8072,
    "grounded_pass_rate": 0.7952,
    "hit@5": 0.9518,
    "p@5_of_ceiling": 0.715,
    "false_validation_rate": 0.1667,  # OI-27: above the 5 % target, must not grow
}


@pytest.fixture(scope="module")
def scorecards(corpus_index_dir: Path) -> dict[Split, dict[str, Any]]:
    # Default settings, not the environment's: the gates describe the shipped configuration.
    settings = Settings(_env_file=None)
    index = load_index(corpus_index_dir)
    assert check_index(index) is None, "gold labels do not match the index; rebuild the gold set"
    return {split: evaluate_split(index, split, settings).scorecard for split in Split}


def test_dev_pool_does_not_regress_from_the_baseline(
    scorecards: dict[Split, dict[str, Any]],
) -> None:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert check_gate(scorecards[Split.DEV], baseline, require_targets=False) == []


@pytest.mark.parametrize("split", list(Split), ids=lambda s: s.value)
def test_sc3_pass_rate_meets_the_target(
    scorecards: dict[Split, dict[str, Any]], split: Split
) -> None:
    assert scorecards[split]["pass_rate"] >= SC3_PASS_RATE


@pytest.mark.parametrize("split", list(Split), ids=lambda s: s.value)
def test_sc2_ceiling_normalised_precision(
    scorecards: dict[Split, dict[str, Any]], split: Split
) -> None:
    assert scorecards[split]["p@5_of_ceiling"] >= MIN_P5_OF_CEILING


def test_dev_pool_has_no_false_validations_beyond_the_limit(
    scorecards: dict[Split, dict[str, Any]],
) -> None:
    assert scorecards[Split.DEV]["false_validation_rate"] <= MAX_FALSE_VALIDATION


@pytest.mark.parametrize("metric", sorted(TEST_SPLIT_RECORD))
def test_held_out_split_matches_its_frozen_record(
    scorecards: dict[Split, dict[str, Any]], metric: str
) -> None:
    value, record = scorecards[Split.TEST][metric], TEST_SPLIT_RECORD[metric]
    if metric == "false_validation_rate":
        assert value <= record + 1e-9, f"more false validations on held-out data: {value:.4f}"
    else:
        assert value >= record - TOLERANCE, f"{metric} regressed: {value:.4f} < {record:.4f}"
