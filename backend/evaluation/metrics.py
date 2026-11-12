"""Ranking and abstention metrics (ADR-0001, ADR-0002). Pure functions, no I/O.

Relevance follows ADR-0001: a chunk is relevant if it has a grade (1 or 2).
* precision@K, recall@K: binary over grade ≥ 1
* nDCG@K: graded gains (2 = answer-bearing, 1 = topically relevant)
* hit@K, MRR: grade-2 ("found the exact answer") only
* ceiling@K: the best precision@K any ranking could reach given |R(q)|
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np


def precision_at_k(ranked: Sequence[str], grades: Mapping[str, int], k: int) -> float:
    return sum(1 for c in ranked[:k] if c in grades) / k


def recall_at_k(ranked: Sequence[str], grades: Mapping[str, int], k: int) -> float:
    if not grades:
        return 0.0
    return sum(1 for c in ranked[:k] if c in grades) / len(grades)


def ceiling_at_k(grades: Mapping[str, int], k: int) -> float:
    return min(len(grades), k) / k


def hit_at_k(ranked: Sequence[str], grades: Mapping[str, int], k: int) -> float:
    return 1.0 if any(grades.get(c) == 2 for c in ranked[:k]) else 0.0


def reciprocal_rank(ranked: Sequence[str], grades: Mapping[str, int]) -> float:
    for rank, chunk_id in enumerate(ranked, start=1):
        if grades.get(chunk_id) == 2:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked: Sequence[str], grades: Mapping[str, int], k: int) -> float:
    def dcg(gains: Sequence[int]) -> float:
        return float(sum((2.0**g - 1.0) / math.log2(i + 2) for i, g in enumerate(gains)))

    ideal = dcg(sorted(grades.values(), reverse=True)[:k])
    if ideal == 0.0:
        return 0.0
    return dcg([grades.get(c, 0) for c in ranked[:k]]) / ideal


@dataclass(frozen=True, slots=True)
class Estimate:
    """A mean with a percentile-bootstrap 95% confidence interval."""

    mean: float
    low: float
    high: float
    n: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "mean": round(self.mean, 4),
            "ci95_low": round(self.low, 4),
            "ci95_high": round(self.high, 4),
            "n": self.n,
        }


def bootstrap(
    values: Sequence[float],
    *,
    statistic: Callable[[np.ndarray], float] = lambda a: float(np.mean(a)),
    resamples: int = 2000,
    seed: int = 20261112,
) -> Estimate:
    """Percentile bootstrap over questions. Seeded, so reports are reproducible."""
    data = np.asarray(values, dtype=np.float64)
    if data.size == 0:
        return Estimate(float("nan"), float("nan"), float("nan"), 0)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, data.size, size=(resamples, data.size))
    stats = np.array([statistic(data[row]) for row in idx])
    low, high = np.percentile(stats, [2.5, 97.5])
    return Estimate(float(statistic(data)), float(low), float(high), int(data.size))
