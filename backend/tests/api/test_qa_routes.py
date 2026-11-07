"""HTTP behaviour of the Phase 0 contract stub."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

ROUTES = ["/api/v1/qa", "/qa"]
PROBLEM_JSON = "application/problem+json"


@pytest.mark.parametrize("path", ROUTES)
def test_valid_request_returns_501_problem(client: TestClient, path: str) -> None:
    resp = client.post(
        path, json={"question": "When should hand hygiene be performed?", "top_k": 5}
    )
    assert resp.status_code == 501
    assert resp.headers["content-type"].startswith(PROBLEM_JSON)
    body = resp.json()
    assert body["status"] == 501
    assert body["title"] == "Not Implemented"
    assert body["instance"] == path


@pytest.mark.parametrize("path", ROUTES)
def test_invalid_request_returns_422_problem_without_echoing_input(
    client: TestClient, path: str
) -> None:
    phi_question = "Patient MRN 12345678 asks?"
    resp = client.post(path, json={"question": phi_question, "top_k": 99})
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith(PROBLEM_JSON)
    body = resp.json()
    assert body["errors"][0]["loc"] == ["body", "top_k"]
    assert phi_question not in resp.text, "rejected input must not be echoed (ADR-0009)"


def test_alias_and_canonical_route_behave_identically(client: TestClient) -> None:
    payloads = [{"question": "Valid question?"}, {"question": "x"}, {}]
    for payload in payloads:
        canonical, alias = (client.post(p, json=payload) for p in ROUTES)
        assert canonical.status_code == alias.status_code
        body_c, body_a = canonical.json(), alias.json()
        body_c.pop("instance")
        body_a.pop("instance")
        assert body_c == body_a


def test_unknown_route_is_problem_json(client: TestClient) -> None:
    resp = client.get("/nope")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith(PROBLEM_JSON)
