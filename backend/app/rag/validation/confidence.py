"""Confidence score and status decision (ADR-0002, revised 2026-11-12).

confidence = w_cov · coverage + w_qs · query_support + w_ret · retrieval_score
validated  ⇔ answer not empty ∧ confidence ≥ threshold ∧ numeric_ok
             (the retrieval floor is applied earlier, before generation)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.api.schemas.qa import AbstentionReason, QAStatus


@dataclass(frozen=True, slots=True)
class ConfidenceWeights:
    coverage: float = 0.40
    query_support: float = 0.35
    retrieval: float = 0.25

    def __post_init__(self) -> None:
        total = self.coverage + self.query_support + self.retrieval
        if min(self.coverage, self.query_support, self.retrieval) < 0 or abs(total - 1.0) > 1e-6:
            raise ValueError("confidence weights must be non-negative and sum to 1.0")


def combine(
    coverage: float, query_support: float, retrieval_score: float, w: ConfidenceWeights
) -> float:
    value = w.coverage * coverage + w.query_support * query_support + w.retrieval * retrieval_score
    return round(min(1.0, max(0.0, value)), 6)


def decide(
    *, answer_empty: bool, confidence: float, numeric_ok: bool, threshold: float
) -> tuple[QAStatus, AbstentionReason | None]:
    """Status plus the most specific reason for abstaining (ADR-0007)."""
    if answer_empty:
        return QAStatus.NEEDS_REVIEW, AbstentionReason.NO_EVIDENCE
    if not numeric_ok:
        return QAStatus.NEEDS_REVIEW, AbstentionReason.NUMERIC_MISMATCH
    if confidence < threshold:
        return QAStatus.NEEDS_REVIEW, AbstentionReason.LOW_CONFIDENCE
    return QAStatus.VALIDATED, None
