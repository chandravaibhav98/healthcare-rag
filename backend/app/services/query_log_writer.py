"""Persisting `/qa` outcomes to `query_log` without slowing the request (plan §2.2).

    request thread ──observe()──► redact + build row ──call_soon_threadsafe──► asyncio.Queue
                                                                                 │
                                         background task: batch insert ◄─────────┘

* The pipeline runs in the threadpool, so the observer hands rows to the event loop
  thread-safely; the writer task inserts them in batches.
* The queue is bounded. When the database is slow or down, rows are dropped and counted
  (`qa_log_dropped_total`) rather than blocking answers: the user's request always wins.
* PHI redaction happens here, before anything leaves the process (ADR-0009).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Callable
from typing import Any, Final

import structlog

from app.core.metrics import Metrics
from app.core.redaction import redact
from app.db.session import Database
from app.repositories import query_log as query_log_repo
from app.services.qa_service import QAOutcome

BATCH_SIZE: Final = 100
_log = structlog.get_logger("qa.query_log_writer")
TopicLookup = Callable[[str], list[str]]


def outcome_to_row(outcome: QAOutcome, topics_for_doc: TopicLookup) -> dict[str, Any]:
    r = outcome.response
    meta = r.meta
    redacted = redact(outcome.question)
    topics = sorted({t for c in r.citations for t in topics_for_doc(c.doc_id)})
    return {
        "request_id": outcome.request_id,
        "user_id": uuid.UUID(outcome.user_id) if outcome.user_id else None,
        "question": redacted.text,
        "redactions": redacted.count,
        "status": r.status.value,
        "reason": meta.reason.value if meta and meta.reason else None,
        "confidence": r.confidence,
        "signals": meta.signals.model_dump() if meta else {},
        "citations": [c.model_dump(mode="json") for c in r.citations],
        "answer": r.answer,
        "candidate_answer": outcome.candidate_answer,
        "topics": topics,
        "top_k": outcome.top_k,
        "latency_ms": round(outcome.latency_s * 1000, 3),
        "index_version": meta.index_version if meta else "unknown",
    }


class QueryLogWriter:
    def __init__(
        self, db: Database, metrics: Metrics | None = None, *, max_queue: int = 10_000
    ) -> None:
        self._db = db
        self._metrics = metrics
        self._max_queue = max_queue
        # Created in start(): an asyncio.Queue binds to the loop that first uses it, and the
        # app's lifespan may run more than once (tests, ASGI servers that restart it).
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_queue)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None

    # -- lifecycle (event loop thread) -------------------------------------------------
    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=self._max_queue)
        self._task = asyncio.create_task(self._run(), name="query-log-writer")

    async def stop(self, timeout_s: float = 5.0) -> None:
        """Flush what is queued (bounded wait), then stop."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.flush(), timeout_s)
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._loop = None  # submits after shutdown are counted as dropped

    async def flush(self) -> None:
        await self._queue.join()

    # -- producer side (any thread) ----------------------------------------------------
    def submit(self, row: dict[str, Any]) -> None:
        if self._loop is None or self._loop.is_closed():
            self._dropped(1)
            return
        self._loop.call_soon_threadsafe(self._enqueue, row)

    def _enqueue(self, row: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(row)
        except asyncio.QueueFull:
            self._dropped(1)

    def _dropped(self, n: int) -> None:
        if self._metrics is not None:
            self._metrics.qa_log_dropped.inc(n)
        _log.warning("qa.query_log_dropped", count=n)

    # -- consumer ------------------------------------------------------------------------
    async def _run(self) -> None:
        while True:
            batch = [await self._queue.get()]
            while len(batch) < BATCH_SIZE and not self._queue.empty():
                batch.append(self._queue.get_nowait())
            try:
                async with self._db.session() as session:
                    query_log_repo.add_many(session, batch)
                    await session.commit()
            except Exception:
                _log.exception("qa.query_log_write_failed", rows=len(batch))
                self._dropped(len(batch))
            finally:
                for _ in batch:
                    self._queue.task_done()


class PersistingQueryObserver:
    """`QAObserver` that redacts the outcome and hands it to the writer."""

    def __init__(self, writer: QueryLogWriter, topics_for_doc: TopicLookup) -> None:
        self._writer = writer
        self._topics = topics_for_doc

    def observe(self, outcome: QAOutcome) -> None:
        self._writer.submit(outcome_to_row(outcome, self._topics))
