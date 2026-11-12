"""Application factory (plan §2.3, Phase 3).

Run with the factory flag so nothing heavy happens at import time:

    uvicorn --factory app.main:create_app

`create_app()` only wires objects. The index is loaded in the lifespan and verified
against its manifest: if the artifacts are missing or a hash does not match, startup
fails and the pod never becomes ready (fail fast, plan Phase 3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.api.errors import PROBLEM_JSON, register_exception_handlers
from app.api.routes.health import router as health_router
from app.api.routes.qa import router as qa_router
from app.api.schemas.qa import CONTRACT_VERSION
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.metrics import Metrics
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import Rate, TokenBucketLimiter
from app.rag.index.registry import IndexRegistry
from app.rag.runtime import build_runtime
from app.services.observers import MetricsObserver, QueryLogObserver
from app.services.qa_service import QAService

API_TITLE = "Healthcare Guidelines RAG Assistant"
API_DESCRIPTION = (
    "Citation-first, evidence-validated question answering over guideline documents.\n\n"
    "> ⚠️ All guideline content is **synthetic**. Not for clinical use."
)
_PROBLEM_REF = "#/components/schemas/ProblemDetails"
_log = structlog.get_logger("app")


def _build_openapi(app: FastAPI) -> dict[str, Any]:
    """OpenAPI with error responses declared as `application/problem+json`.

    FastAPI documents every response model under `application/json`. The real error
    media type is set here so the published contract matches the wire (ADR-0006). Only
    ProblemDetails bodies are converted: `/readyz` returns its own model with 503.
    """
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=API_TITLE,
        version=CONTRACT_VERSION,
        description=API_DESCRIPTION,
        routes=app.routes,
    )
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            for code, response in operation.get("responses", {}).items():
                content = response.get("content", {})
                body = content.get("application/json", {})
                if code[:1] in {"4", "5"} and body.get("schema", {}).get("$ref") == _PROBLEM_REF:
                    response["content"] = {PROBLEM_JSON: body}
    app.openapi_schema = schema
    return schema


def _lifespan(settings: Settings) -> Any:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        registry: IndexRegistry = app.state.registry
        if not registry.is_loaded:
            # Verification hashes every artifact; keep it off the event loop.
            runtime = await run_in_threadpool(registry.load, settings.index_dir)
            _log.info(
                "index.loaded", index_version=runtime.index_version, path=str(settings.index_dir)
            )
        app.state.metrics.set_index(registry.current().index_version)
        yield

    return lifespan


def create_app(settings: Settings | None = None, registry: IndexRegistry | None = None) -> FastAPI:
    """Build the app. Tests pass `settings` and a pre-loaded `registry`."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    registry = registry or IndexRegistry(lambda index: build_runtime(index, settings))
    metrics = Metrics()

    # `version` is the CONTRACT version, not the build version, so the committed
    # OpenAPI snapshot changes only when the contract does.
    app = FastAPI(
        title=API_TITLE,
        version=CONTRACT_VERSION,
        description=API_DESCRIPTION,
        lifespan=_lifespan(settings),
    )
    app.state.build_version = __version__
    app.state.settings = settings
    app.state.registry = registry
    app.state.metrics = metrics
    app.state.qa_limiter = TokenBucketLimiter(Rate.parse(settings.rate_limit_qa))
    app.state.qa_service = QAService(
        registry,
        threshold=settings.confidence_threshold,
        retrieval_floor=settings.retrieval_floor,
        observers=(
            MetricsObserver(metrics),
            QueryLogObserver(log_question_text=settings.log_question_text),
        ),
    )

    register_exception_handlers(app)
    app.include_router(qa_router)
    app.include_router(health_router)
    if settings.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        async def metrics_endpoint() -> Response:
            return Response(metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")

    # Middleware order: the last added runs first. CORS must see preflights before
    # anything else; the request context wraps every other response.
    app.add_middleware(RequestContextMiddleware, metrics=metrics)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
        allow_credentials=True,
        max_age=600,
    )
    app.openapi = lambda: _build_openapi(app)  # type: ignore[method-assign]
    return app
