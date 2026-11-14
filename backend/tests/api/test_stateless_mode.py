"""Without DATABASE_URL the service stays useful: /qa works, persistence routes say 503."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

AppFactory = Callable[..., FastAPI]  # the `app_factory` fixture (tests/conftest.py)


def test_qa_works_and_persistence_routes_are_503(app_factory: AppFactory) -> None:
    with TestClient(app_factory(database_url="")) as client:
        assert client.post("/qa", json={"question": "hand hygiene?"}).status_code == 200
        for method, path in [
            ("POST", "/api/v1/auth/login"),
            ("GET", "/api/v1/admin/stats"),
            ("GET", "/api/v1/auth/me"),
            ("POST", "/api/v1/escalations"),
        ]:
            resp = client.request(method, path, json={"email": "a@b.co", "password": "x"})
            assert resp.status_code in (401, 503), (path, resp.status_code)
        assert (
            client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x"}).status_code
            == 503
        )
        ready = client.get("/readyz").json()
        assert ready["checks"]["database"] == "not_configured"
        assert ready["status"] == "ready"


def test_a_bearer_token_without_a_database_is_503(app_factory: AppFactory) -> None:
    with TestClient(app_factory(database_url="")) as client:
        resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer x"})
        assert resp.status_code == 503
