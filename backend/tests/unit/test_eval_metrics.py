"""Ranking metrics and bootstrap CIs (ADR-0001 semantics)."""

from __future__ import annotations

import math

import pytest

from evaluation import metrics as m

GRADES = {"a": 2, "b": 1, "c": 1}
RANKED = ["x", "a", "b", "y", "z", "c"]


def test_precision_and_recall_count_both_grades() -> None:
    assert m.precision_at_k(RANKED, GRADES, 5) == pytest.approx(2 / 5)
    assert m.recall_at_k(RANKED, GRADES, 5) == pytest.approx(2 / 3)
    assert m.recall_at_k(RANKED, {}, 5) == 0.0


def test_ceiling_reflects_the_size_of_the_relevant_set() -> None:
    assert m.ceiling_at_k(GRADES, 5) == pytest.approx(3 / 5)
    assert m.ceiling_at_k({str(i): 1 for i in range(9)}, 5) == 1.0


def test_hit_and_reciprocal_rank_use_grade_two_only() -> None:
    assert m.hit_at_k(RANKED, GRADES, 1) == 0.0
    assert m.hit_at_k(RANKED, GRADES, 2) == 1.0
    assert m.reciprocal_rank(RANKED, GRADES) == pytest.approx(1 / 2)
    assert m.reciprocal_rank(["b", "c"], GRADES) == 0.0  # only grade 1 found


def test_ndcg_is_one_for_the_ideal_ranking() -> None:
    assert m.ndcg_at_k(["a", "b", "c"], GRADES, 5) == pytest.approx(1.0)
    assert m.ndcg_at_k(["c", "b", "a"], GRADES, 5) < 1.0
    expected = (3 / math.log2(3) + 1 / math.log2(4)) / (3 + 1 / math.log2(3) + 1 / math.log2(4))
    assert m.ndcg_at_k(["x", "a", "b"], GRADES, 3) == pytest.approx(expected)
    assert m.ndcg_at_k(["x"], {}, 5) == 0.0


def test_bootstrap_is_deterministic_and_brackets_the_mean() -> None:
    values = [0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 0.0]
    first, second = m.bootstrap(values), m.bootstrap(values)
    assert first == second
    assert first.low <= first.mean <= first.high
    assert first.n == len(values)
    assert math.isnan(m.bootstrap([]).mean)
