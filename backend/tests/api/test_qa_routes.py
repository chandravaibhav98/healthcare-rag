"""HTTP behaviour of `/qa` (contract v1.1, ADR-0006/0007)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.schemas.qa import ABSTENTION_MESSAGE, QAResponse

ROUTES = ["/api/v1/qa", "/qa"]
PROBLEM_JSON = "application/problem+json"
ANSWERABLE = "How long should hand hygiene with alcohol-based handrub take?"
OFF_TOPIC = "What is the recommended dose of the yellow fever vaccine?"

AppFactory = Callable[..., FastAPI]  # the `app_factory` fixture (tests/conftest.py)


@pytest.mark.parametrize("path", ROUTES)
def test_answerable_question_is_validated(client: TestClient, path: str) -> None:
    resp = client.post(path, json={"question": ANSWERABLE, "top_k": 5})
    assert resp.status_code == 200
    body = QAResponse.model_validate(resp.json())  # schema-valid
    assert body.status == "validated"
    assert body.citations
    assert body.meta is not None
    assert body.meta.request_id == resp.headers["x-request-id"]


@pytest.mark.parametrize("path", ROUTES)
def test_unanswerable_question_abstains_with_candidates(client: TestClient, path: str) -> None:
    resp = client.post(path, json={"question": OFF_TOPIC})
    assert resp.status_code == 200
    body = QAResponse.model_validate(resp.json())
    assert body.status == "needs_review"
    assert body.answer == ABSTENTION_MESSAGE
    assert body.meta is not None
    assert body.meta.abstained
    assert body.meta.reason is not None


def test_top_level_contract_keys_are_exact(client: TestClient) -> None:
    body = client.post("/qa", json={"question": ANSWERABLE}).json()
    assert set(body) == {"answer", "citations", "confidence", "status", "meta"}


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
    assert body["request_id"] == resp.headers["x-request-id"]
    assert phi_question not in resp.text, "rejected input must not be echoed (ADR-0009)"


@pytest.mark.parametrize(
    "payload",
    [{}, {"question": "x"}, {"question": "a" * 1001}, {"question": "ok?", "top_k": 0}],
)
def test_bounds_are_enforced(client: TestClient, payload: dict[str, object]) -> None:
    assert client.post("/api/v1/qa", json=payload).status_code == 422


def test_alias_and_canonical_route_behave_identically(client: TestClient) -> None:
    payloads = [{"question": ANSWERABLE}, {"question": OFF_TOPIC}, {"question": "x"}, {}]
    for payload in payloads:
        canonical, alias = (client.post(p, json=payload) for p in ROUTES)
        assert canonical.status_code == alias.status_code
        body_c, body_a = canonical.json(), alias.json()
        for body in (body_c, body_a):
            body.pop("instance", None)
            body.pop("request_id", None)
            meta = body.get("meta") or {}
            meta.pop("request_id", None)
            meta.pop("latency_ms", None)
        assert body_c == body_a


def test_index_not_loaded_returns_503_problem(app_factory: AppFactory) -> None:
    app = app_factory(preload=False)
    # No `with`: the lifespan (which would load the index) is deliberately not run.
    client = TestClient(app)
    resp = client.post("/qa", json={"question": ANSWERABLE})
    assert resp.status_code == 503
    assert resp.headers["content-type"].startswith(PROBLEM_JSON)
    assert resp.headers["retry-after"] == "5"
    assert client.get("/readyz").status_code == 503


def test_rate_limit_returns_429_with_retry_after(app_factory: AppFactory) -> None:
    with TestClient(app_factory(rate_limit_qa="2/minute")) as client:
        codes = [client.post("/qa", json={"question": ANSWERABLE}).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        resp = client.post("/api/v1/qa", json={"question": ANSWERABLE})  # shared bucket
        assert resp.status_code == 429
        assert int(resp.headers["retry-after"]) >= 1
        assert resp.headers["content-type"].startswith(PROBLEM_JSON)
        assert client.get("/healthz").status_code == 200  # probes are never limited


def test_unexpected_error_is_a_generic_500_problem(app_factory: AppFactory) -> None:
    from app.api.deps import get_qa_service

    app = app_factory()

    class Broken:
        def answer(self, *_: object) -> None:
            raise RuntimeError("secret internal detail")

    app.dependency_overrides[get_qa_service] = lambda: Broken()
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post(
            "/qa", json={"question": ANSWERABLE}, headers={"X-Request-ID": "abc-123"}
        )
    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith(PROBLEM_JSON)
    assert resp.headers["x-request-id"] == "abc-123"
    assert resp.json()["request_id"] == "abc-123"
    assert "secret internal detail" not in resp.text


def test_unknown_route_is_problem_json(client: TestClient) -> None:
    resp = client.get("/nope")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith(PROBLEM_JSON)
