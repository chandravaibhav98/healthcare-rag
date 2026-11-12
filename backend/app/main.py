"""Application factory (plan §2.3, Phases 3 and 5).

Run with the factory flag so nothing heavy happens at import time:

    uvicorn --factory app.main:create_app

`create_app()` only wires objects. The lifespan loads and verifies the index (fail fast),
and, when DATABASE_URL is set, checks the schema is migrated to head, starts the query-log
writer, registers index versions, applies the latest runtime config and starts the
background loops (config/index poller, retention purge). Without DATABASE_URL the service
runs stateless: `/qa` works, auth and admin routes answer 503.
"""

from __future__ import annotations

import asyncio
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
from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.qa import router as qa_router
from app.api.schemas.qa import CONTRACT_VERSION
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.metrics import Metrics
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import Rate, TokenBucketLimiter
from app.core.tasks import PeriodicTask
from app.db.migrations import SchemaNotAtHeadError, head_revision
from app.db.session import Database
from app.rag.index.registry import IndexRegistry
from app.rag.pipeline import BuildConfig, build_index
from app.rag.runtime import build_runtime
from app.services import maintenance
from app.services.auth_service import AuthService
from app.services.config_service import ConfigService
from app.services.eval_service import EvalService
from app.services.index_service import IndexService
from app.services.observers import MetricsObserver, QueryLogObserver
from app.services.qa_service import QAObserver, QAService
from app.services.query_log_writer import PersistingQueryObserver, QueryLogWriter
from app.services.tuning import Tuning, TuningHolder

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


class _TopicLookup:
    """doc_id → topics of the ACTIVE index (query-log rows record what users ask about)."""

    def __init__(self, registry: IndexRegistry) -> None:
        self._registry = registry
        self._version: str | None = None
        self._topics: dict[str, list[str]] = {}

    def __call__(self, doc_id: str) -> list[str]:
        runtime = self._registry.current()
        if runtime.index_version != self._version:
            documents = runtime.index.manifest["corpus"]["documents"]
            self._topics = {str(d["doc_id"]): list(d.get("topic", [])) for d in documents}
            self._version = runtime.index_version
        return self._topics.get(doc_id, [])


async def _start_persistence(app: FastAPI, settings: Settings, db: Database) -> list[PeriodicTask]:
    revision = await db.schema_revision()
    head = head_revision()
    if revision != head:
        raise SchemaNotAtHeadError(
            f"database schema is at {revision or 'nothing'}, code expects {head}; "
            "run scripts/db-migrate.sh (or .ps1) first"
        )
    app.state.query_log_writer.start()
    index_service: IndexService = app.state.index_service
    config_service: ConfigService = app.state.config_service
    async with db.session() as session:
        await index_service.register_known(session)
        await config_service.sync(session)

    async def poll() -> None:
        # Follow changes made through another pod: runtime config and active index.
        async with db.session() as session:
            await config_service.sync(session)
            if await index_service.sync_active(session):
                app.state.metrics.set_index(app.state.registry.current().index_version)

    async def purge() -> None:
        await maintenance.purge(db, settings.query_log_retention_days)

    tasks = [
        PeriodicTask("config-poller", settings.config_poll_seconds, poll),
        PeriodicTask("retention-purge", settings.retention_purge_interval_minutes * 60, purge),
    ]
    for task in tasks:
        task.start()
    return tasks


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
        db: Database | None = app.state.db
        tasks: list[PeriodicTask] = []
        if db is not None:
            try:
                tasks = await _start_persistence(app, settings, db)
            except BaseException:
                await db.dispose()  # do not leak connections when startup fails
                raise
        try:
            yield
        finally:
            for task in tasks:
                await task.stop()
            if db is not None:
                await app.state.query_log_writer.stop()
                for pending in (
                    app.state.eval_service.wait(),
                    app.state.index_service.wait_for_rebuild(),
                ):
                    try:
                        await asyncio.wait_for(pending, timeout=10)
                    except TimeoutError:
                        _log.warning("shutdown.background_task_timeout")
                await db.dispose()

    return lifespan


def create_app(
    settings: Settings | None = None,
    registry: IndexRegistry | None = None,
    db: Database | None = None,
) -> FastAPI:
    """Build the app. Tests pass `settings`, a pre-loaded `registry` and optionally a
    `Database` (otherwise one is created from DATABASE_URL, if set)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    registry = registry or IndexRegistry(lambda index: build_runtime(index, settings))
    metrics = Metrics()
    if db is None and settings.database_url is not None:
        db = Database(settings.database_url.get_secret_value())

    # `version` is the CONTRACT version, not the build version, so the committed
    # OpenAPI snapshot changes only when the contract does.
    app = FastAPI(
        title=API_TITLE,
        version=CONTRACT_VERSION,
        description=API_DESCRIPTION,
        lifespan=_lifespan(settings),
    )
    tuning = TuningHolder(Tuning.from_settings(settings))
    observers: list[QAObserver] = [
        MetricsObserver(metrics),
        QueryLogObserver(log_question_text=settings.log_question_text),
    ]
    if db is not None:
        writer = QueryLogWriter(db, metrics, max_queue=settings.query_log_queue_size)
        observers.append(PersistingQueryObserver(writer, _TopicLookup(registry)))
        app.state.query_log_writer = writer

    app.state.build_version = __version__
    app.state.settings = settings
    app.state.registry = registry
    app.state.metrics = metrics
    app.state.db = db
    app.state.tuning = tuning
    app.state.qa_limiter = TokenBucketLimiter(Rate.parse(settings.rate_limit_qa))
    app.state.login_limiter = TokenBucketLimiter(Rate.parse(settings.login_rate_limit))
    app.state.qa_service = QAService(registry, tuning=tuning, observers=tuple(observers))
    app.state.auth_service = AuthService(settings)
    app.state.config_service = ConfigService(tuning, Tuning.from_settings(settings))
    app.state.index_service = IndexService(
        registry,
        boot_dir=settings.index_dir,
        store_dir=settings.index_store_dir,
        corpus_dir=settings.corpus_dir,
        build=lambda corpus, out: build_index(corpus, out, BuildConfig.from_settings(settings)),
    )
    app.state.eval_service = EvalService(registry, settings, tuning)

    register_exception_handlers(app)
    app.include_router(qa_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
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
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
        allow_credentials=True,
        max_age=600,
    )
    app.openapi = lambda: _build_openapi(app)  # type: ignore[method-assign]
    return app


__all__ = ["create_app"]
