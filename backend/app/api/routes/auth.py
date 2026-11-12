"""Auth routes (ADR-0008): login, refresh with rotation, logout, current user.

The refresh token travels in an httpOnly, SameSite=Strict cookie scoped to /api/v1/auth,
so page scripts cannot read it and other routes never receive it. It is also returned in
the body for non-browser clients (CLI, tests); the SPA keeps only the access token, in
memory.
"""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import APIRouter, Body, Cookie, Depends, HTTPException, Response, status

from app.api.deps import (
    ActorDep,
    AuthServiceDep,
    CurrentUserDep,
    SessionDep,
    SettingsDep,
    enforce_login_rate_limit,
)
from app.api.errors import problem_responses
from app.api.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserOut
from app.core.config import Settings
from app.services.auth_service import AuthError, IssuedTokens

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

REFRESH_COOKIE: Final = "hcrag_refresh"
COOKIE_PATH: Final = "/api/v1/auth"
_UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


def _set_refresh_cookie(response: Response, tokens: IssuedTokens, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=settings.jwt_refresh_ttl_days * 86_400,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _token_response(tokens: IssuedTokens) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.access_expires_in,
        refresh_token=tokens.refresh_token,
        refresh_expires_at=tokens.refresh_expires_at,
        user=UserOut.model_validate(tokens.user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    operation_id="login",
    summary="Exchange email and password for tokens",
    responses=problem_responses(401, 422, 429, 503),
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def login(
    body: LoginRequest,
    response: Response,
    session: SessionDep,
    auth: AuthServiceDep,
    actor: ActorDep,
    settings: SettingsDep,
) -> TokenResponse:
    try:
        tokens = await auth.login(session, body.email, body.password, actor)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc), _UNAUTHORIZED) from exc
    _set_refresh_cookie(response, tokens, settings)
    return _token_response(tokens)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    operation_id="refresh_tokens",
    summary="Rotate the refresh token and issue a new access token",
    description="Reads the refresh token from the cookie or the body. Each refresh token "
    "works once; presenting a used one revokes the whole session (theft signal).",
    responses=problem_responses(401, 422, 503),
)
async def refresh(
    response: Response,
    session: SessionDep,
    auth: AuthServiceDep,
    actor: ActorDep,
    settings: SettingsDep,
    body: Annotated[RefreshRequest | None, Body()] = None,
    cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse:
    token = (body.refresh_token if body else None) or cookie
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token.", _UNAUTHORIZED)
    try:
        tokens = await auth.refresh(session, token, actor)
    except AuthError as exc:
        response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc), _UNAUTHORIZED) from exc
    _set_refresh_cookie(response, tokens, settings)
    return _token_response(tokens)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="logout",
    summary="Revoke the current session (refresh-token family)",
    responses=problem_responses(503),
)
async def logout(
    response: Response,
    session: SessionDep,
    auth: AuthServiceDep,
    actor: ActorDep,
    body: Annotated[RefreshRequest | None, Body()] = None,
    cookie: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> Response:
    await auth.logout(session, (body.refresh_token if body else None) or cookie, actor)
    response.status_code = status.HTTP_204_NO_CONTENT
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return response


@router.get(
    "/me",
    response_model=UserOut,
    operation_id="current_user",
    summary="The authenticated user",
    responses=problem_responses(401, 503),
)
async def me(user: CurrentUserDep) -> UserOut:
    return UserOut.model_validate(user)
