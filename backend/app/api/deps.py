"""FastAPI dependencies. Every collaborator lives on `app.state` (set up by `create_app`),
so tests can swap any of them with `app.dependency_overrides` or a custom factory call."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.rate_limit import TokenBucketLimiter
from app.rag.index.registry import IndexRegistry
from app.services.qa_service import QAService


def get_registry(request: Request) -> IndexRegistry:
    registry: IndexRegistry = request.app.state.registry
    return registry


def get_qa_service(request: Request) -> QAService:
    service: QAService = request.app.state.qa_service
    return service


def get_request_id(request: Request) -> str:
    request_id: str = request.scope.get("state", {}).get("request_id", "") or "unknown"
    return request_id


def enforce_qa_rate_limit(request: Request) -> None:
    """Per-client token bucket. The key is the peer address; behind a reverse proxy
    run uvicorn with `--proxy-headers --forwarded-allow-ips` so this is the real client."""
    limiter: TokenBucketLimiter = request.app.state.qa_limiter
    limiter.hit(request.client.host if request.client else "anonymous")


RegistryDep = Annotated[IndexRegistry, Depends(get_registry)]
QAServiceDep = Annotated[QAService, Depends(get_qa_service)]
RequestIdDep = Annotated[str, Depends(get_request_id)]
