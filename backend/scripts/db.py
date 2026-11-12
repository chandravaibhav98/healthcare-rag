"""Database migrations CLI (wrapped by scripts/db-migrate.sh / .ps1).

    uv run python scripts/db.py upgrade [--revision head]
    uv run python scripts/db.py downgrade <revision>
    uv run python scripts/db.py current

The URL comes from DATABASE_URL (.env or environment). For SQLite the parent folder is
created first, since SQLite will not create directories.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from alembic import command

from app.core.config import get_settings
from app.db.migrations import _XArgs, alembic_config, head_revision
from app.db.session import Database


def _url() -> str:
    url = get_settings().database_url
    if url is None:
        raise SystemExit("DATABASE_URL is empty: nothing to migrate (the API runs stateless).")
    value = url.get_secret_value()
    prefix, sep, path = value.partition(":///")
    if sep and prefix.startswith("sqlite") and path and path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return value


def _redacted(url: str) -> str:
    from sqlalchemy.engine import make_url

    return make_url(url).render_as_string(hide_password=True)


async def _current(url: str) -> str | None:
    db = Database(url)
    try:
        return await db.schema_revision()
    finally:
        await db.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("upgrade", help="migrate forward (default: to head)")
    up.add_argument("--revision", default="head")
    down = sub.add_parser("downgrade", help="migrate back (e.g. -1 or base)")
    down.add_argument("revision")
    sub.add_parser("current", help="show the database and code revisions")
    args = parser.parse_args(argv)

    url = _url()
    cfg = alembic_config()
    cfg.cmd_opts = _XArgs(url)  # type: ignore[assignment]
    print(f"database: {_redacted(url)}")
    if args.cmd == "upgrade":
        command.upgrade(cfg, args.revision)
    elif args.cmd == "downgrade":
        if get_settings().app_env.value == "production":
            raise SystemExit("refusing to downgrade a production database from this script")
        command.downgrade(cfg, args.revision)
    current = asyncio.run(_current(url))
    head = head_revision()
    print(f"revision: {current or 'none'} (code head: {head})")
    return 0 if args.cmd != "current" or current == head else 1


if __name__ == "__main__":
    sys.exit(main())
