"""User escalation of an answer to human review (Phase 6, ADR-0007)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EscalationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
        description="`meta.request_id` of the answer (also the X-Request-ID header).",
    )
    note: str = Field(
        default="",
        max_length=1000,
        description="Why the answer needs checking. Redacted before storage (ADR-0009).",
    )


class EscalationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    status: Literal["queued"] = "queued"
    escalated_at: datetime
