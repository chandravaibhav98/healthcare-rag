"""The query-log writer never blocks answers: a full queue drops and counts rows."""

from __future__ import annotations

import asyncio

from app.core.metrics import Metrics
from app.db.session import Database
from app.services.query_log_writer import QueryLogWriter


def test_full_queue_drops_and_counts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    metrics = Metrics()
    db = Database(f"sqlite+aiosqlite:///{(tmp_path / 'x.db').as_posix()}")

    async def scenario() -> None:
        writer = QueryLogWriter(db, metrics, max_queue=1)
        writer._loop = asyncio.get_running_loop()  # consumer deliberately not started
        writer.submit({"row": 1})
        writer.submit({"row": 2})
        await asyncio.sleep(0)  # let call_soon_threadsafe callbacks run
        await db.dispose()

    asyncio.run(scenario())
    assert "qa_log_dropped_total 1.0" in metrics.render().decode()


def test_submit_before_start_is_dropped_not_raised(tmp_path) -> None:  # type: ignore[no-untyped-def]
    metrics = Metrics()
    writer = QueryLogWriter(Database(f"sqlite+aiosqlite:///{tmp_path}/y.db"), metrics)
    writer.submit({"row": 1})
    assert "qa_log_dropped_total 1.0" in metrics.render().decode()
