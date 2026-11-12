"""Passwords (Argon2id), JWTs (HS256) and roles (plan §4 Phase 5, ADR-0008).

* Passwords: argon2-cffi defaults (Argon2id, RFC 9106 low-memory profile). Hashes are
  re-computed on login when the parameters change (`needs_rehash`).
* Tokens: short-lived access tokens (Authorization: Bearer) and longer-lived refresh
  tokens (httpOnly cookie). Both carry `typ` so one can never be used as the other.
* Roles are ordered: admin ⊇ reviewer ⊇ user.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

ISSUER: Final = "healthcare-rag"
ALGORITHM: Final = "HS256"
_hasher = PasswordHasher()
# Verified when the e-mail is unknown, so a failed login costs the same either way
# (no account enumeration through response timing).
_DUMMY_HASH: Final = _hasher.hash("dummy-password-for-timing")


class Role(StrEnum):
    USER = "user"
    REVIEWER = "reviewer"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return {Role.USER: 0, Role.REVIEWER: 1, Role.ADMIN: 2}[self]

    def allows(self, required: Role) -> bool:
        return self.rank >= required.rank


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class InvalidTokenError(Exception):
    """The token is malformed, expired, of the wrong type or wrongly signed."""


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject: str
    role: Role
    token_type: TokenType
    jti: str
    expires_at: datetime
    family: str | None = None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def create_token(
    *,
    subject: str,
    role: Role,
    token_type: TokenType,
    secret: str,
    ttl: timedelta,
    family: str | None = None,
    now: datetime | None = None,
) -> tuple[str, TokenClaims]:
    issued = now or datetime.now(UTC)
    claims = TokenClaims(
        subject=subject,
        role=role,
        token_type=token_type,
        jti=uuid.uuid4().hex,
        expires_at=issued + ttl,
        family=family,
    )
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "sub": subject,
        "role": role.value,
        "typ": token_type.value,
        "jti": claims.jti,
        "iat": int(issued.timestamp()),
        "exp": int(claims.expires_at.timestamp()),
    }
    if family:
        payload["fam"] = family
    return jwt.encode(payload, secret, algorithm=ALGORITHM), claims


def decode_token(token: str, *, secret: str, expected: TokenType) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "jti", "typ", "iss"]},
        )
        if payload.get("typ") != expected.value:
            raise InvalidTokenError(f"expected a {expected.value} token")
        return TokenClaims(
            subject=str(payload["sub"]),
            role=Role(payload["role"]),
            token_type=expected,
            jti=str(payload["jti"]),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), UTC),
            family=payload.get("fam"),
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise InvalidTokenError(str(exc)) from exc
