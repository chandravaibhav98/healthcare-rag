"""Validation building blocks (ADR-0002): tokenisation, coverage, numbers, support, confidence."""

from __future__ import annotations

import pytest

from app.api.schemas.qa import AbstentionReason, QAStatus
from app.rag.retrieval.expansion import QueryExpander
from app.rag.validation.confidence import ConfidenceWeights, combine, decide
from app.rag.validation.coverage import coverage
from app.rag.validation.numeric import numeric_consistency
from app.rag.validation.support import query_support
from app.rag.validation.tokenize import (
    content_tokens,
    numeric_tokens,
    question_key_terms,
    strip_citation_markers,
)


def test_citation_markers_are_not_content() -> None:
    assert strip_citation_markers("Wash hands [1]. Dry them [12].") == "Wash hands. Dry them."
    assert content_tokens("hands [1]") == content_tokens("hands")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Rub for 20–30 seconds.", {"20-30 s"}),
        ("Store at 2 to 8 °C.", {"2-8 °c"}),
        ("Use 1,000 ppm chlorine.", {"1000 ppm"}),
        ("70% alcohol", {"70 %"}),
        ("within 24 hours", {"24 h"}),
        ("\u221220 °C freezer", {"-20 °c"}),  # Unicode minus sign
        ("a 2-dose series", {"2 dose"}),
    ],
)
def test_numeric_tokens_are_canonical(text: str, expected: set[str]) -> None:
    assert numeric_tokens(text) == expected


def test_numbers_inside_identifiers_are_ignored() -> None:
    assert numeric_tokens("See section 4.2a and who-ipc-004") == frozenset()


def test_numeric_gate_flags_a_number_absent_from_evidence() -> None:
    evidence = ["Perform hand hygiene for 20–30 seconds."]
    assert numeric_consistency("Rub for 20-30 seconds [1].", evidence).ok
    check = numeric_consistency("Rub for 40-60 seconds [1].", evidence)
    assert not check.ok
    assert check.unsupported == ("40-60 s",)


def test_numeric_gate_passes_answers_without_numbers() -> None:
    assert numeric_consistency("Change gloves between patients.", []).ok


def test_coverage_basic_properties() -> None:
    assert coverage("", ["anything"]) == 0.0
    assert coverage("gloves hands", ["gloves and hands"]) == 1.0
    assert coverage("gloves hands", ["gloves only"]) == pytest.approx(0.5)


def test_interrogative_phrases_are_not_key_terms() -> None:
    assert question_key_terms("How long should handrub take?") == question_key_terms("handrub take")


def test_query_support_uses_synonym_groups() -> None:
    expander = QueryExpander.from_file()
    evidence = ["Doffing personal protective equipment follows a fixed sequence."]
    plain = query_support("How do I take off PPE?", evidence, None)
    expanded = query_support("How do I take off PPE?", evidence, expander)
    assert expanded > plain


def test_idf_weighting_punishes_a_missing_specific_term() -> None:
    question = "recommended dose of ibuprofen"
    evidence = ["The recommended dose is in the schedule."]
    idf = {"recommend": 0.2, "dose": 0.5, "ibuprofen": 3.0}
    plain = query_support(question, evidence, None)
    weighted = query_support(question, evidence, None, lambda t: idf.get(t, 1.0))
    assert plain == pytest.approx(2 / 3)
    assert weighted == pytest.approx(0.7 / 3.7)


def test_query_support_of_empty_question_is_zero() -> None:
    assert query_support("what is the?", ["text"], None) == 0.0


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        ConfidenceWeights(0.5, 0.5, 0.5)
    with pytest.raises(ValueError, match="non-negative"):
        ConfidenceWeights(1.2, -0.1, -0.1)


def test_combine_is_weighted_and_clamped() -> None:
    w = ConfidenceWeights()
    assert combine(1.0, 1.0, 1.0, w) == 1.0
    assert combine(0.0, 0.0, 0.0, w) == 0.0
    assert combine(1.0, 0.5, 0.2, w) == pytest.approx(0.4 + 0.175 + 0.05)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {"answer_empty": True, "confidence": 0.9, "numeric_ok": True},
            AbstentionReason.NO_EVIDENCE,
        ),
        (
            {"answer_empty": False, "confidence": 0.9, "numeric_ok": False},
            AbstentionReason.NUMERIC_MISMATCH,
        ),
        (
            {"answer_empty": False, "confidence": 0.59, "numeric_ok": True},
            AbstentionReason.LOW_CONFIDENCE,
        ),
        ({"answer_empty": False, "confidence": 0.6, "numeric_ok": True}, None),
    ],
)
def test_decide_reports_the_most_specific_reason(
    kwargs: dict[str, object], expected: AbstentionReason | None
) -> None:
    status, reason = decide(threshold=0.6, **kwargs)  # type: ignore[arg-type]
    assert reason == expected
    assert status is (QAStatus.VALIDATED if expected is None else QAStatus.NEEDS_REVIEW)
