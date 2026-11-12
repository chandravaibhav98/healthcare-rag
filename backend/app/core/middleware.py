"""Request-context middleware (pure ASGI, so there is no per-request BaseHTTPMiddleware overhead).

For every HTTP request it:
* takes a safe incoming `X-Request-ID` or generates one, binds it to the structlog
  context and echoes it in the response;
* adds security headers (and `Cache-Control: no-store` on API responses, because answers
  may relate to a patient question);
* records HTTP metrics by route *template* (bounded label cardinality) and writes one
  access-log line without the query string or body (ADR-0009).
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Final

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.metrics import Metrics

_SAFE_ID: Final = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_DOC_PATHS: Final = ("/docs", "/redoc", "/openapi.json")
_BASE_HEADERS: Final = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
)
_API_CSP: Final = b"default-src 'none'; frame-ancestors 'none'"
_log = structlog.get_logger("http")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, metrics: Metrics | None = None) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        path: str = scope.get("path", "")
        is_docs = path.startswith(_DOC_PATHS)
        started = time.perf_counter()
        status_code = 500
        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                headers.extend(_BASE_HEADERS)
                if not is_docs:  # Swagger UI needs scripts; API responses need nothing
                    headers.append((b"content-security-policy", _API_CSP))
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - started
            route = getattr(scope.get("route"), "path", None) or "unmatched"
            if self.metrics is not None:
                self.metrics.observe_http(
                    method=scope["method"],
                    route=route,
                    status_code=status_code,
                    duration_s=duration,
                )
            _log.info(
                "http.request",
                method=scope["method"],
                route=route,
                status_code=status_code,
                duration_ms=round(duration * 1000, 2),
            )
            structlog.contextvars.unbind_contextvars("request_id")
