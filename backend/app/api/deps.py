"""FastAPI dependencies. Every collaborator lives on `app.state` (set up by `create_app`),
so tests can swap any of them with `app.dependency_overrides` or a custom factory call.

Auth (ADR-0008): bearer access tokens. The user is re-read from the database on every
request, so deactivation or a role change applies at once rather than at token expiry.
Persistence is optional: without DATABASE_URL, `/qa` still works anonymously and every
auth/admin route answers 503.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Callable, Collection
from enum import StrEnum
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.rate_limit import TokenBucketLimiter
from app.core.security import Role
from app.db.models import User
from app.db.session import Database
from app.rag.index.registry import IndexRegistry
from app.repositories.audit import Actor
from app.repositories.paging import PageRequest
from app.services.auth_service import AuthError, AuthService
from app.services.qa_service import QAService

MAX_PAGE_SIZE = 200
#: Marks routes where a bearer token is optional; the OpenAPI builder (app.main) turns it
#: into `security: [{}, {bearerAuth: []}]` (anonymous OR bearer).
OPTIONAL_AUTH: dict[str, object] = {"x-optional-auth": True}
_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="bearerAuth",
    description="Access token from POST /api/v1/auth/login.",
)
_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_registry(request: Request) -> IndexRegistry:
    registry: IndexRegistry = request.app.state.registry
    return registry


def get_qa_service(request: Request) -> QAService:
    service: QAService = request.app.state.qa_service
    return service


def get_request_id(request: Request) -> str:
    request_id: str = request.scope.get("state", {}).get("request_id", "") or "unknown"
    return request_id


def enforce_qa_rate_limit(request: Request) -> None:
    """Per-client token bucket. The key is the peer address; behind a reverse proxy
    run uvicorn with `--proxy-headers --forwarded-allow-ips` so this is the real client."""
    limiter: TokenBucketLimiter = request.app.state.qa_limiter
    limiter.hit(_client_ip(request) or "anonymous")


def enforce_login_rate_limit(request: Request) -> None:
    """Slows password guessing per client address. In-process, so per pod; a shared
    limit across replicas needs Redis (plan Open Issues)."""
    limiter: TokenBucketLimiter = request.app.state.login_limiter
    limiter.hit(_client_ip(request) or "anonymous")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# --- persistence -----------------------------------------------------------------
def get_db(request: Request) -> Database:
    db: Database | None = request.app.state.db
    if db is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistence is not configured on this deployment (DATABASE_URL).",
        )
    return db


async def get_session(db: Annotated[Database, Depends(get_db)]) -> AsyncIterator[AsyncSession]:
    async with db.session() as session:
        yield session


def get_auth_service(request: Request) -> AuthService:
    service: AuthService = request.app.state.auth_service
    return service


# --- authentication and RBAC --------------------------------------------------------
async def get_optional_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User | None:
    """The caller, or None when no bearer token was sent. A token that IS sent must be
    valid: a bad token is a 401, never a silent downgrade to anonymous."""
    if credentials is None:
        return None
    db = get_db(request)
    auth = get_auth_service(request)
    async with db.session() as session:
        try:
            user = await auth.user_from_access_token(session, credentials.credentials)
        except AuthError as exc:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, detail=str(exc), headers=_UNAUTHORIZED_HEADERS
            ) from exc
    request.scope.setdefault("state", {})["user_id"] = str(user.id)
    return user


async def get_current_user(
    user: Annotated[User | None, Depends(get_optional_user)],
) -> User:
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers=_UNAUTHORIZED_HEADERS,
        )
    return user


def require_role(required: Role) -> Callable[..., User]:
    """Dependency factory: the caller must hold `required` or a higher role
    (admin ⊇ reviewer ⊇ user)."""

    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not Role(user.role).allows(required):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail=f"Requires the '{required.value}' role."
            )
        return user

    dependency.__name__ = f"require_{required.value}"
    return dependency


def get_actor(request: Request, user: Annotated[User | None, Depends(get_optional_user)]) -> Actor:
    return Actor(
        id=user.id if user else None,
        email=user.email if user else None,
        request_id=get_request_id(request),
        ip=_client_ip(request),
    )


# --- pagination ------------------------------------------------------------------------
#: Offsets beyond this are rejected (422) rather than overflowing a database integer.
MAX_OFFSET = 1_000_000


def page_params(
    sortable: Collection[str], default: str, *, name: str
) -> Callable[..., PageRequest]:
    """Dependency factory for `limit`, `offset`, `sort`, `order`.

    `sort` is published as an enum of the allowed columns, so the OpenAPI contract says
    exactly which values are valid (Schemathesis checks this). The signature is built
    explicitly because the enum is created at runtime and `from __future__ import
    annotations` would turn a closure annotation into an unresolvable string.
    """
    allowed = sorted(sortable)
    sort_enum = StrEnum(name, {column: column for column in allowed})  # type: ignore[misc]

    def dependency(limit: int, offset: int, sort: StrEnum, order: str) -> PageRequest:
        return PageRequest(
            limit=limit, offset=offset, sort=str(sort.value), descending=order == "desc"
        )

    dependency.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [
            inspect.Parameter(
                "limit",
                inspect.Parameter.KEYWORD_ONLY,
                default=50,
                annotation=Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)],
            ),
            inspect.Parameter(
                "offset",
                inspect.Parameter.KEYWORD_ONLY,
                default=0,
                annotation=Annotated[int, Query(ge=0, le=MAX_OFFSET)],
            ),
            inspect.Parameter(
                "sort",
                inspect.Parameter.KEYWORD_ONLY,
                default=sort_enum(default),
                annotation=Annotated[sort_enum, Query(description="Column to sort by.")],
            ),
            inspect.Parameter(
                "order",
                inspect.Parameter.KEYWORD_ONLY,
                default="desc",
                annotation=Annotated[Literal["asc", "desc"], Query()],
            ),
        ],
        return_annotation=PageRequest,
    )
    return dependency


RegistryDep = Annotated[IndexRegistry, Depends(get_registry)]
QAServiceDep = Annotated[QAService, Depends(get_qa_service)]
RequestIdDep = Annotated[str, Depends(get_request_id)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DbDep = Annotated[Database, Depends(get_db)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
ActorDep = Annotated[Actor, Depends(get_actor)]
ReviewerDep = Annotated[User, Depends(require_role(Role.REVIEWER))]
AdminDep = Annotated[User, Depends(require_role(Role.ADMIN))]
