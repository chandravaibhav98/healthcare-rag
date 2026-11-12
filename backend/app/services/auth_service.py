"""Login, token refresh with rotation and reuse detection, logout (ADR-0008).

Refresh tokens are one-time-use: every refresh revokes the presented token and issues a
new one in the same *family* (one login session). If an already-revoked token is
presented again, someone replayed a stolen copy, so the whole family is revoked and the
user must log in again. All outcomes are audit-logged; failures never reveal whether the
e-mail exists.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    InvalidTokenError,
    Role,
    TokenType,
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.db.base import utcnow
from app.db.models import User
from app.repositories import audit
from app.repositories import tokens as token_repo
from app.repositories import users as user_repo
from app.repositories.audit import Actor


class AuthError(Exception):
    """Authentication failed. The message is safe to show to the client."""


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_at: datetime
    refresh_jti: str
    user: User


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret.get_secret_value()
        self._access_ttl = timedelta(minutes=settings.jwt_access_ttl_minutes)
        self._refresh_ttl = timedelta(days=settings.jwt_refresh_ttl_days)

    def _issue(self, session: AsyncSession, user: User, family: str) -> IssuedTokens:
        role = Role(user.role)
        access, _ = create_token(
            subject=str(user.id),
            role=role,
            token_type=TokenType.ACCESS,
            secret=self._secret,
            ttl=self._access_ttl,
        )
        refresh, claims = create_token(
            subject=str(user.id),
            role=role,
            token_type=TokenType.REFRESH,
            secret=self._secret,
            ttl=self._refresh_ttl,
            family=family,
        )
        token_repo.add(
            session, jti=claims.jti, user_id=user.id, family_id=family, expires_at=claims.expires_at
        )
        return IssuedTokens(
            access,
            int(self._access_ttl.total_seconds()),
            refresh,
            claims.expires_at,
            claims.jti,
            user,
        )

    async def login(
        self, session: AsyncSession, email: str, password: str, actor: Actor
    ) -> IssuedTokens:
        user = await user_repo.get_by_email(session, email)
        ok = verify_password(password, user.password_hash if user else None)
        if user is None or not ok or not user.is_active:
            audit.record(
                session,
                Actor(
                    email=user_repo.normalise_email(email), request_id=actor.request_id, ip=actor.ip
                ),
                "auth.login_failed",
                details={"reason": "inactive" if user and ok else "bad_credentials"},
            )
            await session.commit()
            raise AuthError("Invalid email or password.")
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        user.last_login_at = utcnow()
        issued = self._issue(session, user, family=uuid.uuid4().hex)
        audit.record(
            session,
            Actor(user.id, user.email, actor.request_id, actor.ip),
            "auth.login",
            target_type="user",
            target_id=str(user.id),
        )
        await session.commit()
        return issued

    async def refresh(
        self, session: AsyncSession, refresh_token: str, actor: Actor
    ) -> IssuedTokens:
        try:
            claims = decode_token(refresh_token, secret=self._secret, expected=TokenType.REFRESH)
        except InvalidTokenError as exc:
            raise AuthError("Invalid or expired session. Please log in again.") from exc
        stored = await token_repo.get(session, claims.jti)
        if stored is None:
            raise AuthError("Invalid or expired session. Please log in again.")
        user = await user_repo.get(session, stored.user_id)
        if stored.revoked_at is not None:
            # Replay of a rotated token: revoke the whole session family.
            await token_repo.revoke_family(session, stored.family_id)
            audit.record(
                session,
                Actor(stored.user_id, user.email if user else None, actor.request_id, actor.ip),
                "auth.refresh_reuse_detected",
                target_type="user",
                target_id=str(stored.user_id),
                details={"family": stored.family_id},
            )
            await session.commit()
            raise AuthError("Session was revoked. Please log in again.")
        if user is None or not user.is_active or stored.expires_at <= datetime.now(UTC):
            raise AuthError("Invalid or expired session. Please log in again.")
        issued = self._issue(session, user, family=stored.family_id)
        stored.revoked_at = utcnow()
        stored.replaced_by = issued.refresh_jti
        await session.commit()
        return issued

    async def logout(self, session: AsyncSession, refresh_token: str | None, actor: Actor) -> None:
        if not refresh_token:
            return
        try:
            claims = decode_token(refresh_token, secret=self._secret, expected=TokenType.REFRESH)
        except InvalidTokenError:
            return
        stored = await token_repo.get(session, claims.jti)
        if stored is not None:
            await token_repo.revoke_family(session, stored.family_id)
            audit.record(
                session,
                Actor(stored.user_id, actor.email, actor.request_id, actor.ip),
                "auth.logout",
                target_type="user",
                target_id=str(stored.user_id),
            )
            await session.commit()

    async def user_from_access_token(self, session: AsyncSession, token: str) -> User:
        try:
            claims = decode_token(token, secret=self._secret, expected=TokenType.ACCESS)
            user_id = uuid.UUID(claims.subject)
        except (InvalidTokenError, ValueError) as exc:
            raise AuthError("Invalid or expired access token.") from exc
        user = await user_repo.get(session, user_id)
        if user is None or not user.is_active:
            raise AuthError("Invalid or expired access token.")
        return user  # role comes from the database, so a demotion applies immediately
