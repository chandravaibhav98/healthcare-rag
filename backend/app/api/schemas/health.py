"""Health, readiness and version payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CheckState = Literal["ok", "fail", "not_configured"]


class Liveness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"] = "ok"


class Readiness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "not_ready"]
    checks: dict[str, CheckState] = Field(
        description="Per-dependency state: `index` (loaded and verified), `database` (`not_configured` when DATABASE_URL is unset)."
    )
    index_version: str | None = None


class VersionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    build_version: str = Field(description="Backend package version.")
    contract_version: str = Field(description="`/qa` API contract version (ADR-0006).")
    index_version: str | None = Field(description="Active index, or null if none is loaded.")
    analysis_version: int = Field(
        description="Text-analysis version (changes vectors and postings)."
    )
