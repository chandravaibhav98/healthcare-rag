"""Error contract: RFC 9457 Problem Details (ADR-0006)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FieldError(BaseModel):
    """One request-validation failure. The rejected input is deliberately NOT echoed
    back, because a question may contain patient information (ADR-0009)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    loc: list[str | int] = Field(description="Path to the offending field, e.g. ['body', 'top_k'].")
    msg: str = Field(description="Human-readable reason.")
    type: str = Field(description="Machine-readable error type, e.g. 'less_than_equal'.")


class ProblemDetails(BaseModel):
    """`application/problem+json` body for every 4xx/5xx response."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "type": "about:blank",
                    "title": "Unprocessable Content",
                    "status": 422,
                    "detail": "Request validation failed.",
                    "errors": [
                        {
                            "loc": ["body", "top_k"],
                            "msg": "Input should be less than or equal to 20",
                            "type": "less_than_equal",
                        }
                    ],
                }
            ]
        },
    )

    type: str = Field(default="about:blank", description="URI identifying the problem type.")
    title: str = Field(description="Short, human-readable summary of the problem type.")
    status: int = Field(ge=100, le=599, description="HTTP status code.")
    detail: str | None = Field(default=None, description="Explanation of this occurrence.")
    instance: str | None = Field(default=None, description="URI of this occurrence (request path).")
    request_id: str | None = Field(default=None, description="Correlation ID (Phase 3).")
    errors: list[FieldError] | None = Field(default=None, description="Validation failures (422).")
