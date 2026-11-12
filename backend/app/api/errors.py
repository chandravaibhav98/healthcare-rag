"""RFC 9457 `application/problem+json` error handling (ADR-0006).

Every error leaves the API in one shape, so clients (and the generated TypeScript
client) need exactly one error type.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, Final

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.schemas.common import FieldError, ProblemDetails
from app.core.rate_limit import RateLimitExceededError
from app.rag.index.registry import IndexNotLoadedError

#: Seconds a client should wait before retrying while the index is loading.
INDEX_RETRY_AFTER_S: Final = 5
_log = structlog.get_logger("errors")

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
    request_id: str | None = None,
) -> JSONResponse:
    body = ProblemDetails(
        title=_title(status),
        status=status,
        detail=detail,
        instance=instance,
        request_id=request_id,
        errors=errors,
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(mode="json", exclude_none=True),
        media_type=PROBLEM_JSON,
        headers=headers,
    )


def _request_id(request: Request) -> str | None:
    value = request.scope.get("state", {}).get("request_id")
    return value if isinstance(value, str) else None


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101  (handler registered for this type)
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem_response(
        exc.status_code,
        detail=detail,
        instance=request.url.path,
        headers=dict(exc.headers) if exc.headers else None,
        request_id=_request_id(request),
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
        422,
        detail="Request validation failed.",
        instance=request.url.path,
        errors=errors,
        request_id=_request_id(request),
    )


async def _index_not_loaded_handler(request: Request, exc: Exception) -> JSONResponse:
    return problem_response(
        503,
        detail="The guideline index is not loaded yet. Retry shortly.",
        instance=request.url.path,
        headers={"Retry-After": str(INDEX_RETRY_AFTER_S)},
        request_id=_request_id(request),
    )


async def _rate_limit_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RateLimitExceededError)  # noqa: S101
    return problem_response(
        429,
        detail="Too many requests. Slow down and retry after the indicated delay.",
        instance=request.url.path,
        headers={"Retry-After": str(int(exc.retry_after_s))},
        request_id=_request_id(request),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Runs in Starlette's outermost ServerErrorMiddleware, i.e. outside our request
    # middleware, so the correlation header is added here explicitly. The exception is
    # logged with its traceback; the client gets no internals (no stack, no message).
    request_id = _request_id(request)
    _log.error("http.unhandled_exception", request_id=request_id, exc_info=exc)
    return problem_response(
        500,
        detail="An unexpected error occurred. Quote the request_id when reporting it.",
        instance=request.url.path,
        headers={"X-Request-ID": request_id} if request_id else None,
        request_id=request_id,
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(IndexNotLoadedError, _index_not_loaded_handler)
    app.add_exception_handler(RateLimitExceededError, _rate_limit_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses=` entries documenting problem+json errors for a route."""
    return {status: {"model": ProblemDetails, "description": _title(status)} for status in statuses}
