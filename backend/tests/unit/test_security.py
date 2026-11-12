"""Passwords (argon2id) and JWTs (ADR-0008)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import (
    ALGORITHM,
    InvalidTokenError,
    Role,
    TokenType,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)

SECRET = "x" * 40


def test_password_hash_round_trip() -> None:
    hashed = hash_password("s3cret pass")
    assert hashed.startswith("$argon2id$")
    assert hashed != hash_password("s3cret pass"), "salted"
    assert verify_password("s3cret pass", hashed)
    assert not verify_password("wrong", hashed)


def test_unknown_user_and_garbage_hash_fail_closed() -> None:
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")


@pytest.mark.parametrize(
    ("caller", "required", "allowed"),
    [
        (Role.ADMIN, Role.REVIEWER, True),
        (Role.ADMIN, Role.ADMIN, True),
        (Role.REVIEWER, Role.REVIEWER, True),
        (Role.REVIEWER, Role.ADMIN, False),
        (Role.USER, Role.REVIEWER, False),
        (Role.USER, Role.USER, True),
    ],
)
def test_role_hierarchy(caller: Role, required: Role, allowed: bool) -> None:
    assert caller.allows(required) is allowed


def _token(
    token_type: TokenType = TokenType.ACCESS,
    ttl: timedelta = timedelta(minutes=5),
    family: str | None = None,
) -> str:
    token, _ = create_token(
        subject="u-1",
        role=Role.REVIEWER,
        token_type=token_type,
        secret=SECRET,
        ttl=ttl,
        family=family,
    )
    return token


def test_token_round_trip() -> None:
    claims = decode_token(_token(), secret=SECRET, expected=TokenType.ACCESS)
    assert claims.subject == "u-1"
    assert claims.role is Role.REVIEWER
    assert claims.expires_at > datetime.now(UTC)
    refresh = decode_token(
        _token(TokenType.REFRESH, family="fam"), secret=SECRET, expected=TokenType.REFRESH
    )
    assert refresh.family == "fam"


def test_token_type_is_enforced() -> None:
    with pytest.raises(InvalidTokenError):
        decode_token(
            _token(TokenType.REFRESH, family="f"), secret=SECRET, expected=TokenType.ACCESS
        )


def test_expired_wrong_key_and_tampered_tokens_are_rejected() -> None:
    with pytest.raises(InvalidTokenError):
        decode_token(_token(ttl=timedelta(seconds=-1)), secret=SECRET, expected=TokenType.ACCESS)
    with pytest.raises(InvalidTokenError):
        decode_token(_token(), secret="y" * 40, expected=TokenType.ACCESS)
    head, payload, sig = _token().split(".")
    with pytest.raises(InvalidTokenError):
        decode_token(f"{head}.{payload}x.{sig}", secret=SECRET, expected=TokenType.ACCESS)


def test_alg_none_and_foreign_issuer_are_rejected() -> None:
    now = datetime.now(UTC)
    claims = {
        "iss": "someone-else",
        "sub": "u",
        "role": "admin",
        "typ": "access",
        "jti": "j",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    forged = jwt.encode(claims, SECRET, algorithm=ALGORITHM)
    with pytest.raises(InvalidTokenError):
        decode_token(forged, secret=SECRET, expected=TokenType.ACCESS)
    unsigned = jwt.encode({**claims, "iss": "healthcare-rag"}, None, algorithm="none")
    with pytest.raises(InvalidTokenError):
        decode_token(unsigned, secret=SECRET, expected=TokenType.ACCESS)
