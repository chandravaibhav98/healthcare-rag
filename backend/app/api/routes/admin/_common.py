from __future__ import annotations

from typing import Any

from fastapi import Request

from app.api.errors import problem_responses
from app.api.schemas.admin import Page
from app.repositories.paging import PageResult

#: Every admin path starts here. Each module router carries the prefix itself (FastAPI
#: >= 0.16x no longer flattens nested routers, and the metrics/log `route` label is the
#: matched route's own path, so it must be the full template).
PREFIX = "/api/v1/admin"

#: Every admin route can answer these.
AUTH_ERRORS = (401, 403, 503)


def responses(*extra: int) -> dict[int | str, dict[str, Any]]:
    return problem_responses(*sorted({*AUTH_ERRORS, *extra}))


def state(request: Request, name: str) -> Any:
    return getattr(request.app.state, name)


def to_page(result: PageResult[Any], convert: Any) -> Page[Any]:
    return Page(
        items=[convert(item) for item in result.items],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )
