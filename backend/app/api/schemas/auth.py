"""Auth payloads (Phase 5, ADR-0008)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RoleName = Literal["user", "reviewer", "admin"]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    """Body is optional: browsers send the httpOnly cookie; other clients send the token."""

    model_config = ConfigDict(extra="forbid")
    refresh_token: str | None = Field(default=None, max_length=4096)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: uuid.UUID
    email: str
    display_name: str
    role: RoleName
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class TokenResponse(BaseModel):
    """`refresh_token` is also set as an httpOnly cookie scoped to /api/v1/auth. It is
    returned in the body for non-browser clients; the SPA must ignore it (ADR-0008)."""

    model_config = ConfigDict(extra="forbid")
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  (OAuth2 token type, not a secret)
    expires_in: int = Field(description="Access-token lifetime in seconds.")
    refresh_token: str
    refresh_expires_at: datetime
    user: UserOut
