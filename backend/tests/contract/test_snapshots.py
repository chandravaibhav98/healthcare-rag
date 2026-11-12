"""The committed snapshots ARE the published contract; code must match them."""

from __future__ import annotations

import json

from scripts.export_schemas import (
    GOLD_SCHEMA_PATH,
    OPENAPI_PATH,
    render_gold_schema,
    render_openapi,
    stale_snapshots,
)


def test_snapshots_are_current() -> None:
    stale = stale_snapshots()
    assert not stale, f"stale snapshots {stale}: run `uv run python scripts/export_schemas.py`"


def test_openapi_exposes_canonical_route_and_spec_alias() -> None:
    paths = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))["paths"]
    assert {"/api/v1/qa", "/qa"} <= set(paths)
    for path in ("/api/v1/qa", "/qa"):
        responses = paths[path]["post"]["responses"]
        assert "application/json" in responses["200"]["content"]
        assert "501" not in responses, "the Phase 0 stub response must be gone"
        for code in ("422", "429", "500", "503"):
            assert set(responses[code]["content"]) == {"application/problem+json"}


def test_readiness_503_keeps_its_own_json_body() -> None:
    paths = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))["paths"]
    content = paths["/readyz"]["get"]["responses"]["503"]["content"]
    assert set(content) == {"application/json"}


def test_openapi_response_schema_keeps_the_four_spec_fields() -> None:
    doc = json.loads(render_openapi())
    qa_response = doc["components"]["schemas"]["QAResponse"]
    assert set(qa_response["required"]) == {"answer", "citations", "confidence", "status"}
    # 1.1.0: additive only (Citation.superseded, documented 429/500/503), so minor bump.
    assert doc["info"]["version"] == "1.1.0"
    assert "superseded" not in doc["components"]["schemas"]["Citation"].get("required", [])


def test_gold_schema_snapshot_is_json_schema() -> None:
    schema = json.loads(GOLD_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema == json.loads(render_gold_schema())
    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["additionalProperties"] is False
