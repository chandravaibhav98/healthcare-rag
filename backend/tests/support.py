"""Helpers for API tests with a database: seeded personas and authenticated calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import Any, Final

from fastapi.testclient import TestClient
from httpx2 import Response

from app.core.security import Role, hash_password
from app.db.session import Database
from app.repositories import users as user_repo

PASSWORD: Final = "correct horse battery staple"  # noqa: S105  (test fixture)


@dataclass(frozen=True, slots=True)
class Persona:
    role: Role
    email: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


async def create_user(db: Database, email: str, role: Role, password: str = PASSWORD) -> None:
    async with db.session() as session:
        user_repo.add(
            session,
            email=email,
            display_name=email.split("@")[0],
            password_hash=hash_password(password),
            role=role.value,
        )
        await session.commit()


@dataclass
class AuthedClient:
    """A TestClient plus one logged-in persona per role."""

    client: TestClient
    personas: dict[Role, Persona] = field(default_factory=dict)

    @classmethod
    def create(cls, client: TestClient) -> AuthedClient:
        out = cls(client)
        for role in Role:
            out.personas[role] = out.add_user(f"{role.value}@example.org", role)
        return out

    @property
    def app(self) -> Any:
        return self.client.app

    @property
    def db(self) -> Database:
        db: Database = self.app.state.db
        return db

    def run(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Run an async callable on the app's event loop (where its tasks live)."""
        return self.client.portal.call(partial(fn, *args, **kwargs))  # type: ignore[union-attr]

    def add_user(self, email: str, role: Role, password: str = PASSWORD) -> Persona:
        self.run(create_user, self.db, email, role, password)
        return Persona(role, email, self.login(email, password).json()["access_token"])

    def login(self, email: str, password: str = PASSWORD) -> Response:
        return self.client.post("/api/v1/auth/login", json={"email": email, "password": password})

    def as_(self, role: Role | None) -> dict[str, str]:
        return self.personas[role].headers if role else {}

    def get(self, path: str, role: Role | None = Role.ADMIN, **kw: Any) -> Response:
        return self.client.get(path, headers=self.as_(role), **kw)

    def post(self, path: str, role: Role | None = Role.ADMIN, **kw: Any) -> Response:
        return self.client.post(path, headers=self.as_(role), **kw)

    def put(self, path: str, role: Role | None = Role.ADMIN, **kw: Any) -> Response:
        return self.client.put(path, headers=self.as_(role), **kw)

    def ask(self, question: str, role: Role | None = None, **kw: Any) -> Response:
        return self.post("/api/v1/qa", role, json={"question": question, **kw})

    def flush_query_log(self) -> None:
        self.run(self.app.state.query_log_writer.flush)
