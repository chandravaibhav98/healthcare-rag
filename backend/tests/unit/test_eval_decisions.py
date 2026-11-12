"""Offline re-scoring, threshold selection and the evaluation gate."""

from __future__ import annotations

from typing import Any

import pytest

from evaluation.eval_validation import keyword_recall, review_list, status_at
from evaluation.run import TOLERANCE, check_gate
from evaluation.svg import line_chart
from evaluation.threshold_sweep import choose, rescore, weight_grid


def _row(answerable: bool, conf: float, reason: str = "", **extra: Any) -> dict[str, Any]:
    base = {
        "id": "q",
        "answerable": answerable,
        "confidence": conf,
        "reason": reason,
        "coverage": 1.0,
        "query_support": conf,
        "retrieval_score": conf,
        "cites_grade2": True,
        "kind": "direct",
        "topic": "t",
        "question": "?",
        "answer": "",
        "citations": "",
    }
    return {**base, **extra}


def test_status_respects_hard_abstentions() -> None:
    assert status_at(_row(True, 0.9), 0.6) == "validated"
    assert status_at(_row(True, 0.5), 0.6) == "needs_review"
    for reason in ("no_evidence", "below_retrieval_floor", "numeric_mismatch"):
        assert status_at(_row(True, 0.99, reason), 0.1) == "needs_review"


def test_rescore_and_choose() -> None:
    rows = [_row(True, 0.9), _row(True, 0.7), _row(False, 0.65), _row(False, 0.2)]
    assert rescore(rows, (0.0, 1.0, 0.0), 0.6) == (1.0, 0.5)
    assert rescore(rows, (0.0, 1.0, 0.0), 0.68) == (1.0, 0.0)
    curve = [
        {"threshold": 0.55, "pass_rate": 1.0, "false_validation_rate": 0.5},
        {"threshold": 0.6, "pass_rate": 0.9, "false_validation_rate": 0.0},
        {"threshold": 0.7, "pass_rate": 0.9, "false_validation_rate": 0.0},
    ]
    assert choose(curve) == curve[1]  # tie on pass rate → closest to the brief's 0.6
    assert choose([{"threshold": 0.5, "pass_rate": 1.0, "false_validation_rate": 0.9}]) is None


def test_weight_grid_sums_to_one() -> None:
    grid = weight_grid(0.25)
    assert len(grid) == 15
    assert all(abs(sum(w) - 1.0) < 1e-9 for w in grid)


def test_keyword_recall_normalises_dashes_and_case() -> None:
    assert keyword_recall("Rub for 20-30 Seconds.", ["20–30 seconds"]) == 1.0
    assert keyword_recall("anything", []) is None
    assert keyword_recall("a b", ["a", "c"]) == pytest.approx(0.5)


def test_review_list_flags_every_wrong_or_borderline_decision() -> None:
    rows = [
        _row(True, 0.5, id="miss"),
        _row(False, 0.9, id="false-valid"),
        _row(True, 0.62, id="borderline"),
        _row(True, 0.9, cites_grade2=False, id="ungrounded"),
        _row(True, 0.9, id="fine"),
    ]
    flagged = {r["id"] for r in review_list(rows, 0.6)}
    assert flagged == {"miss", "false-valid", "borderline", "ungrounded"}


BASE = {
    "p@5": 0.6,
    "hit@5": 0.99,
    "ndcg@5": 0.79,
    "pass_rate": 0.92,
    "grounded_pass_rate": 0.89,
    "false_validation_rate": 0.0,
}


def test_gate_passes_on_equal_metrics_and_fails_on_regressions() -> None:
    assert check_gate(dict(BASE), BASE, require_targets=False) == []
    worse = {**BASE, "pass_rate": BASE["pass_rate"] - 2 * TOLERANCE}
    assert any("pass_rate" in f for f in check_gate(worse, BASE, require_targets=False))
    unsafe = {**BASE, "false_validation_rate": 0.1}
    assert len(check_gate(unsafe, BASE, require_targets=False)) == 2


def test_gate_can_require_the_literal_targets() -> None:
    failures = check_gate(dict(BASE), BASE, require_targets=True)
    assert failures == ["SC2: P@5 0.6000 < 0.65"]


def test_svg_chart_is_well_formed_text() -> None:
    svg = line_chart(
        "t", [0.1, 0.2], {"a": [0.0, 1.0]}, x_label="x", y_label="y", markers={"m": 0.15}
    )
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "polyline" in svg
