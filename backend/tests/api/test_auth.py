"""Auth flows (ADR-0008): login, rotation, reuse detection, logout, RBAC freshness."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.api.routes.auth import COOKIE_PATH, REFRESH_COOKIE
from app.core.security import Role
from app.db.models import AuditLog, User
from app.db.session import Database
from tests.support import PASSWORD, AuthedClient

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


async def _actions(db: Database) -> list[str]:
    async with db.session() as s:
        return list((await s.execute(select(AuditLog.action).order_by(AuditLog.id))).scalars())


async def _set_user(db: Database, email: str, **values: object) -> None:
    async with db.session() as s:
        await s.execute(update(User).where(User.email == email).values(**values))
        await s.commit()


def test_login_returns_tokens_cookie_and_user(api: AuthedClient) -> None:
    resp = api.login("admin@example.org")
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"  # noqa: S105
    assert body["expires_in"] == 15 * 60
    assert body["user"]["role"] == "admin"
    assert "password_hash" not in body["user"]
    cookie = resp.headers["set-cookie"]
    assert f"{REFRESH_COOKIE}=" in cookie
    assert "HttpOnly" in cookie
    assert f"Path={COOKIE_PATH}" in cookie
    assert "samesite=strict" in cookie.lower()
    assert "Secure" not in cookie  # test environment; automatic Secure outside dev/test


def test_email_is_case_insensitive(api: AuthedClient) -> None:
    assert api.login("  Admin@Example.ORG ").status_code == 200


@pytest.mark.parametrize(
    ("email", "password"),
    [("admin@example.org", "wrong password"), ("nobody@example.org", PASSWORD)],
)
def test_bad_credentials_are_401_and_audited(api: AuthedClient, email: str, password: str) -> None:
    resp = api.login(email, password)
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"
    assert resp.json()["detail"] == "Invalid email or password."  # same message: no user oracle
    assert api.run(_actions, api.db)[-1] == "auth.login_failed"


def test_inactive_user_cannot_log_in_or_use_existing_token(api: AuthedClient) -> None:
    api.run(_set_user, api.db, "user@example.org", is_active=False)
    assert api.login("user@example.org").status_code == 401
    assert api.get(ME, Role.USER).status_code == 401


def test_me_requires_a_valid_token(api: AuthedClient) -> None:
    assert api.get(ME, None).status_code == 401
    me = api.get(ME, Role.REVIEWER)
    assert me.status_code == 200
    assert me.json()["email"] == "reviewer@example.org"
    bad = api.client.get(ME, headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(api: AuthedClient) -> None:
    refresh = api.login("user@example.org").json()["refresh_token"]
    resp = api.client.get(ME, headers={"Authorization": f"Bearer {refresh}"})
    assert resp.status_code == 401


def test_role_change_applies_immediately(api: AuthedClient) -> None:
    assert api.get("/api/v1/admin/audit-log", Role.ADMIN).status_code == 200
    api.run(_set_user, api.db, "admin@example.org", role="user")
    assert api.get("/api/v1/admin/audit-log", Role.ADMIN).status_code == 403


def test_refresh_rotates_and_reuse_revokes_the_family(api: AuthedClient) -> None:
    first = api.login("user@example.org").json()["refresh_token"]
    rotated = api.client.post(REFRESH, json={"refresh_token": first})
    assert rotated.status_code == 200
    second = rotated.json()["refresh_token"]
    assert second != first

    # Replaying the used token is a theft signal: it fails AND kills the live one.
    replay = api.client.post(REFRESH, json={"refresh_token": first})
    assert replay.status_code == 401
    assert api.client.post(REFRESH, json={"refresh_token": second}).status_code == 401
    assert "auth.refresh_reuse_detected" in api.run(_actions, api.db)


def test_refresh_reads_the_cookie(
    db_app_factory: Callable[..., FastAPI], sqlite_database_url: str
) -> None:
    with TestClient(db_app_factory(sqlite_database_url)) as client:
        authed = AuthedClient.create(client)
        authed.login("admin@example.org")  # sets the cookie on the client jar
        # The jar keeps the cookie for its path only; the client sends it to /auth/*.
        resp = client.post(REFRESH)
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == "admin@example.org"


def test_refresh_without_token_is_401(api: AuthedClient) -> None:
    api.client.cookies.clear()
    assert api.client.post(REFRESH).status_code == 401
    assert api.client.post(REFRESH, json={"refresh_token": "garbage"}).status_code == 401


def test_logout_revokes_the_session(api: AuthedClient) -> None:
    token = api.login("reviewer@example.org").json()["refresh_token"]
    assert api.client.post(LOGOUT, json={"refresh_token": token}).status_code == 204
    assert api.client.post(REFRESH, json={"refresh_token": token}).status_code == 401
    assert "auth.logout" in api.run(_actions, api.db)
    # Logging out twice or without a token is harmless.
    assert api.client.post(LOGOUT).status_code == 204


def test_login_is_rate_limited(
    db_app_factory: Callable[..., FastAPI], sqlite_database_url: str
) -> None:
    app = db_app_factory(sqlite_database_url, login_rate_limit="2/minute")
    with TestClient(app) as client:
        codes = [
            client.post(LOGIN, json={"email": "x@example.org", "password": "y"}).status_code
            for _ in range(3)
        ]
    assert codes == [401, 401, 429]


def test_anonymous_qa_can_be_disabled(
    db_app_factory: Callable[..., FastAPI], sqlite_database_url: str
) -> None:
    app = db_app_factory(sqlite_database_url, allow_anonymous_qa=False)
    with TestClient(app) as client:
        authed = AuthedClient.create(client)
        question = {"question": "When should health workers perform hand hygiene?"}
        assert client.post("/api/v1/qa", json=question).status_code == 401
        assert authed.post("/api/v1/qa", Role.USER, json=question).status_code == 200


def test_qa_rejects_an_invalid_token_instead_of_downgrading(api: AuthedClient) -> None:
    resp = api.client.post(
        "/qa", json={"question": "hand hygiene?"}, headers={"Authorization": "Bearer nope"}
    )
    assert resp.status_code == 401
