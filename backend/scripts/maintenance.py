"""Maintenance jobs (ADR-0009). The API also runs the purge periodically; this CLI is for
cron / a Kubernetes CronJob and for running it on demand.

    uv run python scripts/maintenance.py purge [--retention-days N]
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.config import get_settings
from app.db.session import Database
from app.services.maintenance import purge


async def _purge(days: int) -> None:
    settings = get_settings()
    if settings.database_url is None:
        raise SystemExit("DATABASE_URL is empty: nothing to purge.")
    db = Database(settings.database_url.get_secret_value())
    try:
        result = await purge(db, days)
    finally:
        await db.dispose()
    print(
        f"purged {result.query_logs} query log rows older than {result.cutoff:%Y-%m-%d %H:%M} "
        f"UTC and {result.refresh_tokens} expired refresh tokens"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Maintenance jobs.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("purge", help="apply the query-log retention period now")
    p.add_argument("--retention-days", type=int, default=None)
    args = parser.parse_args(argv)
    days = args.retention_days or get_settings().query_log_retention_days
    if days < 1:
        parser.error("--retention-days must be >= 1")
    asyncio.run(_purge(days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
