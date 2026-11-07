"""RFC 9457 `application/problem+json` error handling (ADR-0006).

Every error leaves the API in one shape, so clients (and the generated TypeScript
client) need exactly one error type.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.schemas.common import FieldError, ProblemDetails

PROBLEM_JSON: Final = "application/problem+json"


def _title(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def problem_response(
    status: int,
    *,
    detail: str | None = None,
    instance: str | None = None,
    errors: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ProblemDetails(
        title=_title(status), status=status, detail=detail, instance=instance, errors=errors
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(mode="json", exclude_none=True),
        media_type=PROBLEM_JSON,
        headers=headers,
    )


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101  (handler registered for this type)
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem_response(
        exc.status_code,
        detail=detail,
        instance=request.url.path,
        headers=dict(exc.headers) if exc.headers else None,
    )


async def _validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    # Only loc/msg/type are returned. The raw `input` is dropped on purpose: echoing a
    # rejected question would put potential PHI into client logs (ADR-0009).
    errors = [
        FieldError(
            loc=list(err.get("loc", ())), msg=str(err.get("msg", "")), type=str(err.get("type", ""))
        )
        for err in exc.errors()
    ]
    return problem_response(
        422, detail="Request validation failed.", instance=request.url.path, errors=errors
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses=` entries documenting problem+json errors for a route."""
    return {status: {"model": ProblemDetails, "description": _title(status)} for status in statuses}
