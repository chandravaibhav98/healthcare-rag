"""Evaluation runs triggered from the admin API (plan Phase 5).

A run evaluates the ACTIVE index with the CURRENT runtime tuning on the dev pool, using
exactly the code of `python -m evaluation.run` (`evaluate_split`). The test split is not
exposed: it is held out and run by hand once per frozen configuration (ADR-0001), so the
dashboard can never be used to tune against it.

Runs execute in the threadpool (CPU-bound) one at a time. State lives in `eval_runs`
(queued → running → succeeded | failed) so every pod and the UI see the same thing. A row
left queued/running by a crashed pod is marked failed after STALE_AFTER, so it cannot
block new runs forever.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Final

import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.db.base import utcnow
from app.db.models import EvalRun
from app.db.session import Database
from app.rag.index.registry import IndexRegistry
from app.rag.pipeline import LoadedIndex
from app.repositories import audit
from app.repositories import eval_runs as run_repo
from app.repositories.audit import Actor
from app.services.tuning import TuningHolder

_log = structlog.get_logger("eval")
STALE_AFTER: Final = timedelta(hours=1)
#: The only split the API may evaluate (the test split stays held out).
API_SPLIT: Final = "dev"

EvalRunner = Callable[[LoadedIndex, Settings], dict[str, Any]]


def default_runner(index: LoadedIndex, settings: Settings) -> dict[str, Any]:
    """Same computation as the CLI; imported lazily so the API starts without it."""
    from evaluation.common import check_index
    from evaluation.eval_validation import review_list
    from evaluation.run import evaluate_split
    from evaluation.schemas import Split

    warning = check_index(index)
    result = evaluate_split(index, Split.DEV, settings)
    summary = result.summary(settings, index.index_version, Split.DEV)
    # The analyst list (low_confidence.csv in CLI runs), for the dashboard.
    summary["low_confidence"] = review_list(result.validation_rows, settings.confidence_threshold)
    if warning:
        summary["warning"] = warning
    return summary


class EvalAlreadyRunningError(Exception):
    def __init__(self, run_id: uuid.UUID) -> None:
        super().__init__(f"evaluation run {run_id} is already in progress")
        self.run_id = run_id


class EvalService:
    def __init__(
        self,
        registry: IndexRegistry,
        settings: Settings,
        tuning: TuningHolder,
        runner: EvalRunner = default_runner,
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._tuning = tuning
        self._runner = runner
        self._task: asyncio.Task[None] | None = None

    def _effective_settings(self) -> Settings:
        """Settings with the live tuning applied, so a run measures what users get."""
        t = self._tuning.get()
        w = t.weights
        update_: dict[str, Any] = {
            "confidence_threshold": t.threshold,
            "retrieval_floor": t.retrieval_floor,
        }
        if w is not None:
            update_ |= {
                "confidence_weight_coverage": w.coverage,
                "confidence_weight_query_support": w.query_support,
                "confidence_weight_retrieval": w.retrieval,
            }
        return self._settings.model_copy(update=update_)

    async def _expire_stale(self, session: AsyncSession) -> None:
        cutoff = utcnow() - STALE_AFTER
        await session.execute(
            update(EvalRun)
            .where(EvalRun.status.in_(("queued", "running")), EvalRun.created_at < cutoff)
            .values(status="failed", finished_at=utcnow(), error="abandoned (stale run)")
        )

    async def start(self, db: Database, actor: Actor) -> EvalRun:
        index = self._registry.current().index  # raises IndexNotLoadedError → 503
        async with db.session() as session:
            await self._expire_stale(session)
            running = await run_repo.active(session)
            if running is not None:
                raise EvalAlreadyRunningError(running.id)
            run = run_repo.add(session, split=API_SPLIT, triggered_by=actor.id)
            run.index_version = index.index_version
            await session.flush()
            audit.record(
                session,
                actor,
                "eval.start",
                target_type="eval_run",
                target_id=str(run.id),
                details={
                    "split": API_SPLIT,
                    "index_version": index.index_version,
                    "tuning_version": self._tuning.get().version,
                },
            )
            await session.commit()
        self._task = asyncio.create_task(
            self._execute(db, run.id, index, self._effective_settings()), name="eval-run"
        )
        return run

    async def wait(self) -> None:
        """Await the in-flight run (tests, graceful shutdown)."""
        if self._task is not None:
            await self._task

    async def _set(self, db: Database, run_id: uuid.UUID, **values: Any) -> None:
        async with db.session() as session:
            await session.execute(update(EvalRun).where(EvalRun.id == run_id).values(**values))
            await session.commit()

    async def _execute(
        self, db: Database, run_id: uuid.UUID, index: LoadedIndex, settings: Settings
    ) -> None:
        await self._set(db, run_id, status="running", started_at=utcnow())
        try:
            summary = await run_in_threadpool(self._runner, index, settings)
        except Exception as exc:  # any failure is reported on the run row
            _log.exception("eval.failed", run_id=str(run_id))
            await self._set(
                db,
                run_id,
                status="failed",
                finished_at=utcnow(),
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        await self._set(
            db,
            run_id,
            status="succeeded",
            finished_at=utcnow(),
            scorecard=summary.get("scorecard"),
            summary=summary,
        )
        _log.info("eval.succeeded", run_id=str(run_id), scorecard=summary.get("scorecard"))
