"""Contract v1 invariants (ADR-0006, ADR-0007)."""

from __future__ import annotations

from typing import Any

import pytest
from app.api.schemas.qa import QARequest, QAResponse, QAStatus
from pydantic import ValidationError

CITATION: dict[str, Any] = {
    "id": 1,
    "doc_id": "who-ipc-004",
    "title": "Glove Use (synthetic)",
    "source_org": "WHO",
    "section_path": "PPE › Gloves",
    "chunk_id": "who-ipc-004::ppe-gloves::0002",
    "snippet": "Perform hand hygiene before donning gloves.",
    "score": 0.8,
}
SIGNALS = {"coverage": 1.0, "query_support": 0.7, "retrieval_score": 0.6, "numeric_ok": True}


def _meta(*, abstained: bool, reason: str | None = None, numeric_ok: bool = True) -> dict[str, Any]:
    return {
        "request_id": "r-1",
        "index_version": "a1b2c3d",
        "latency_ms": 12.5,
        "abstained": abstained,
        "reason": reason,
        "signals": {**SIGNALS, "numeric_ok": numeric_ok},
    }


def _response(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "answer": "Perform hand hygiene before donning gloves [1].",
        "citations": [CITATION],
        "confidence": 0.78,
        "status": "validated",
        "meta": _meta(abstained=False),
    }
    return {**base, **overrides}


# ---------------------------------------------------------------- request ----


def test_request_defaults_and_strips_whitespace() -> None:
    req = QARequest.model_validate({"question": "   What PPE is required?  "})
    assert req.question == "What PPE is required?"
    assert req.top_k == 5


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "hi"},  # below min length after strip
        {"question": "x" * 1001},
        {"question": "valid question", "top_k": 0},
        {"question": "valid question", "top_k": 21},
        {"question": "valid question", "extra": True},  # extra fields forbidden
        {"top_k": 5},
    ],
)
def test_request_rejects_out_of_contract_payloads(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        QARequest.model_validate(payload)


# --------------------------------------------------------------- response ----


def test_spec_fields_are_required_top_level() -> None:
    required = set(QAResponse.model_json_schema()["required"])
    assert required == {"answer", "citations", "confidence", "status"}


def test_valid_validated_response() -> None:
    resp = QAResponse.model_validate(_response())
    assert resp.status is QAStatus.VALIDATED


def test_valid_abstention_keeps_candidate_citations() -> None:
    resp = QAResponse.model_validate(
        _response(
            answer="The indexed guidelines do not contain sufficient evidence to answer this confidently.",
            confidence=0.31,
            status="needs_review",
            meta=_meta(abstained=True, reason="low_confidence"),
        )
    )
    assert resp.citations, "abstentions still surface candidate sources (ADR-0007)"


def test_meta_is_optional() -> None:
    assert QAResponse.model_validate(_response(meta=None)).meta is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"answer": "See [2]."}, "unknown citation ids"),
        ({"citations": [{**CITATION, "id": 2}]}, "1..n in order"),
        ({"citations": [], "answer": "No markers."}, "at least one source"),
        ({"meta": _meta(abstained=True, reason="low_confidence")}, "meta.abstained"),
        ({"meta": _meta(abstained=False, numeric_ok=False)}, "numeric consistency"),
        ({"meta": _meta(abstained=False, reason="low_confidence")}, "if and only if"),
        ({"confidence": 1.2}, "less than or equal to 1"),
        ({"citations": [{**CITATION, "chunk_id": "bad id"}]}, "String should match pattern"),
    ],
)
def test_response_invariants(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        QAResponse.model_validate(_response(**overrides))
