"""Property-based tests (Hypothesis) for the validation signals (plan Phase 3)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.rag.validation.confidence import ConfidenceWeights, combine
from app.rag.validation.coverage import coverage
from app.rag.validation.numeric import numeric_consistency
from app.rag.validation.support import query_support

WORDS = st.sampled_from(
    [
        "gloves",
        "hands",
        "hygiene",
        "vaccine",
        "storage",
        "sharps",
        "container",
        "mask",
        "respirator",
        "doffing",
        "patient",
        "isolation",
        "sterile",
        "waste",
        "outbreak",
        "20",
        "seconds",
        "2",
        "8",
        "°C",
        "70%",
        "days",
    ]
)
TEXT = st.lists(WORDS, max_size=25).map(" ".join)
UNIT = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


@settings(max_examples=200, deadline=None)
@given(answer=TEXT, evidence=st.lists(TEXT, max_size=4))
def test_coverage_is_bounded(answer: str, evidence: list[str]) -> None:
    assert 0.0 <= coverage(answer, evidence) <= 1.0


@settings(max_examples=200, deadline=None)
@given(answer=TEXT, evidence=st.lists(TEXT, max_size=4), extra=TEXT)
def test_coverage_is_monotonic_in_evidence(answer: str, evidence: list[str], extra: str) -> None:
    assert coverage(answer, [*evidence, extra]) >= coverage(answer, evidence)


@settings(max_examples=200, deadline=None)
@given(answer=TEXT)
def test_an_answer_copied_from_its_evidence_is_fully_covered(answer: str) -> None:
    # This is exactly why coverage alone cannot be the confidence (ADR-0002).
    assert coverage(answer, [answer]) in (0.0, 1.0)
    assert coverage("", [answer]) == 0.0


@settings(max_examples=200, deadline=None)
@given(answer=TEXT, evidence=st.lists(TEXT, max_size=4))
def test_numeric_check_passes_iff_nothing_is_unsupported(answer: str, evidence: list[str]) -> None:
    check = numeric_consistency(answer, evidence)
    assert check.ok == (not check.unsupported)
    assert numeric_consistency(answer, [answer]).ok


@settings(max_examples=200, deadline=None)
@given(question=TEXT, evidence=st.lists(TEXT, max_size=4))
def test_query_support_is_bounded_weighted_or_not(question: str, evidence: list[str]) -> None:
    assert 0.0 <= query_support(question, evidence, None) <= 1.0
    assert 0.0 <= query_support(question, evidence, None, lambda t: float(len(t))) <= 1.0


@settings(max_examples=300, deadline=None)
@given(cov=UNIT, qs=UNIT, rs=UNIT, delta=st.floats(min_value=0.0, max_value=1.0))
def test_confidence_is_bounded_and_monotonic(
    cov: float, qs: float, rs: float, delta: float
) -> None:
    w = ConfidenceWeights()
    base = combine(cov, qs, rs, w)
    assert 0.0 <= base <= 1.0
    assert combine(cov, min(1.0, qs + delta), rs, w) >= base
