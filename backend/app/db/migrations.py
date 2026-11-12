"""Programmatic access to the Alembic migrations (startup check, tests, seed CLI).

The API never migrates on startup: with several replicas that would race. Deployments
run `scripts/db-migrate.*` (a Job in Kubernetes) first; the API only checks that the
schema is at head and refuses to start otherwise (fail fast, like the index manifest).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_DIR: Final = Path(__file__).resolve().parents[2]
ALEMBIC_INI: Final = BACKEND_DIR / "alembic.ini"


class SchemaNotAtHeadError(RuntimeError):
    pass


def alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["configure_logger"] = False  # keep the app's logging setup
    return cfg


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if head is None:
        raise RuntimeError("no Alembic migrations found")
    return head


def upgrade(url: str, revision: str = "head") -> None:
    """Run migrations synchronously (must not be called from a running event loop)."""
    cfg = alembic_config()
    cfg.cmd_opts = _XArgs(url)  # type: ignore[assignment]
    command.upgrade(cfg, revision)


class _XArgs:
    """Minimal stand-in for argparse options so env.py's `-x url=...` path is used."""

    def __init__(self, url: str) -> None:
        self.x = [f"url={url}"]
