"""Health probes, version, metrics and cross-cutting HTTP behaviour."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.schemas.qa import CONTRACT_VERSION

AppFactory = Callable[..., FastAPI]  # the `app_factory` fixture (tests/conftest.py)


def test_liveness(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readiness_reports_index(client: TestClient) -> None:
    body = client.get("/readyz").json()
    assert body["status"] == "ready"
    assert body["checks"] == {"index": "ok", "database": "not_configured"}
    assert len(body["index_version"]) == 12


def test_version(client: TestClient) -> None:
    body = client.get("/version").json()
    assert body["contract_version"] == CONTRACT_VERSION
    assert body["index_version"] == client.get("/readyz").json()["index_version"]


def test_lifespan_loads_index_from_settings(app_factory: AppFactory) -> None:
    with TestClient(app_factory(preload=False)) as client:
        assert client.get("/readyz").status_code == 200


def test_lifespan_fails_fast_on_missing_index(app_factory: AppFactory, tmp_path: Path) -> None:
    app = app_factory(preload=False, index_dir=tmp_path / "missing")
    with pytest.raises(FileNotFoundError), TestClient(app):
        pass


def test_request_id_is_echoed_when_safe_and_replaced_when_not(client: TestClient) -> None:
    assert (
        client.get("/healthz", headers={"X-Request-ID": "trace.42_a-b"}).headers["x-request-id"]
        == "trace.42_a-b"
    )
    generated = client.get("/healthz", headers={"X-Request-ID": "bad id\nwith\nnewlines"})
    assert generated.headers["x-request-id"] != "bad id\nwith\nnewlines"
    assert len(generated.headers["x-request-id"]) == 32


def test_security_headers(client: TestClient) -> None:
    headers = client.post("/qa", json={"question": "Gloves?"}).headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["cache-control"] == "no-store"
    assert "default-src 'none'" in headers["content-security-policy"]
    # Swagger UI needs scripts, so the docs keep their own policy.
    assert "content-security-policy" not in client.get("/docs").headers


def test_cors_allows_configured_origin_only(client: TestClient) -> None:
    preflight = {"Access-Control-Request-Method": "POST"}
    ok = client.options("/qa", headers={"Origin": "http://localhost:5173", **preflight})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    denied = client.options("/qa", headers={"Origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in denied.headers


def test_metrics_exposes_qa_and_http_series(client: TestClient) -> None:
    client.post("/qa", json={"question": "How long should handrub take?"})
    text = client.get("/metrics").text
    assert "qa_requests_total" in text
    assert "qa_confidence_bucket" in text
    assert 'http_requests_total{method="POST",route="/qa"' in text
    assert "rag_index_info{index_version=" in text


def test_metrics_can_be_disabled(app_factory: AppFactory) -> None:
    with TestClient(app_factory(metrics_enabled=False)) as client:
        assert client.get("/metrics").status_code == 404


def test_metrics_and_probes_are_not_in_the_public_contract(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/metrics" not in paths
    assert {"/healthz", "/readyz", "/version", "/qa", "/api/v1/qa"} <= set(paths)
