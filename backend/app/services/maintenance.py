"""Retention (ADR-0009): delete query logs past QUERY_LOG_RETENTION_DAYS and expired
refresh tokens. Revoked tokens stay until they expire, so a replayed one is still recognised
as reuse (and revokes its family) rather than as an unknown token. Runs periodically inside the API and as a CLI/CronJob:

    uv run python -m scripts.maintenance purge
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog

from app.db.base import utcnow
from app.db.session import Database
from app.repositories import audit
from app.repositories import query_log as query_repo
from app.repositories import tokens as token_repo
from app.repositories.audit import SYSTEM

_log = structlog.get_logger("retention")


@dataclass(frozen=True, slots=True)
class PurgeResult:
    cutoff: datetime
    query_logs: int
    refresh_tokens: int


async def purge(db: Database, retention_days: int, now: datetime | None = None) -> PurgeResult:
    now = now or utcnow()
    cutoff = now - timedelta(days=retention_days)
    async with db.session() as session:
        logs = await query_repo.delete_older_than(session, cutoff)
        tokens = await token_repo.delete_expired(session, now)
        if logs or tokens:  # audit only real deletions, so an idle loop does not flood the log
            audit.record(
                session,
                SYSTEM,
                "retention.purge",
                details={
                    "cutoff": cutoff.isoformat(),
                    "query_logs": logs,
                    "refresh_tokens": tokens,
                    "retention_days": retention_days,
                },
            )
        await session.commit()
    result = PurgeResult(cutoff, logs, tokens)
    _log.info("retention.purged", query_logs=logs, refresh_tokens=tokens, cutoff=cutoff.isoformat())
    return result
