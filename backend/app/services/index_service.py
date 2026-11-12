"""Index versions: registration, activation (hot swap) and dev-only rebuilds.

* The boot index (INDEX_DIR) and every complete build under INDEX_STORE_DIR/<version>/ are
  registered in `index_versions` at startup.
* Activating a version verifies and loads it into the `IndexRegistry` (in-flight requests
  finish on the old one), marks it active and audits the change. Other pods follow
  through the config poller (`sync_active`).
* Rebuilding from the admin API is for compose/dev only; in production new versions are
  built by CI and shipped as images (ADR-0008), and the API only lists and activates.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db.base import utcnow
from app.db.models import IndexVersion
from app.db.session import Database
from app.rag.index.manifest import MANIFEST_NAME, read_manifest
from app.rag.index.registry import IndexRegistry
from app.repositories import audit
from app.repositories import index_versions as version_repo
from app.repositories.audit import SYSTEM, Actor

_log = structlog.get_logger("index")
BuildFn = Callable[[Path, Path], Any]


class UnknownIndexVersionError(Exception):
    pass


class RebuildInProgressError(Exception):
    pass


@dataclass
class RebuildState:
    running: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_version: str | None = None
    last_error: str | None = None
    history: list[str] = field(default_factory=list)


class IndexService:
    def __init__(
        self,
        registry: IndexRegistry,
        *,
        boot_dir: Path,
        store_dir: Path,
        corpus_dir: Path,
        build: BuildFn,
    ) -> None:
        self._registry = registry
        self._boot_dir = boot_dir
        self._store_dir = store_dir
        self._corpus_dir = corpus_dir
        self._build = build
        self.rebuild_state = RebuildState()
        self._rebuild_task: asyncio.Task[None] | None = None

    def _candidates(self) -> list[tuple[Path, str]]:
        found = [(self._boot_dir, "boot")]
        if self._store_dir.is_dir():
            found += [
                (p, "store")
                for p in sorted(self._store_dir.iterdir())
                if (p / MANIFEST_NAME).is_file()
            ]
        return found

    async def register_known(self, session: AsyncSession) -> None:
        """Register boot + stored builds and mark the loaded one active."""
        for path, source in self._candidates():
            try:
                manifest = read_manifest(path)
            except (FileNotFoundError, ValueError):
                continue
            await version_repo.register(
                session,
                version=manifest["index_version"],
                path=str(path),
                manifest=manifest,
                source=source,
            )
        if self._registry.is_loaded:
            current = self._registry.current().index_version
            active = await version_repo.active(session)
            if active is None:
                await session.flush()
                await version_repo.set_active(session, current)
        await session.commit()

    async def versions(self, session: AsyncSession) -> Sequence[IndexVersion]:
        return await version_repo.all_versions(session)

    async def activate(self, session: AsyncSession, version: str, actor: Actor) -> IndexVersion:
        row = await version_repo.get(session, version)
        if row is None:
            raise UnknownIndexVersionError(version)
        previous = self._registry.current().index_version if self._registry.is_loaded else None
        await run_in_threadpool(self._registry.load, Path(row.path))  # verifies hashes first
        await version_repo.set_active(session, version)
        audit.record(
            session,
            actor,
            "index.activate",
            target_type="index_version",
            target_id=version,
            details={"previous": previous, "path": row.path},
        )
        await session.commit()
        await session.refresh(row)
        _log.info("index.activated", version=version, previous=previous)
        return row

    async def sync_active(self, session: AsyncSession) -> bool:
        """Follow an activation made on another pod. True if this pod switched."""
        active = await version_repo.active(session)
        if active is None or not self._registry.is_loaded:
            return False
        if active.version == self._registry.current().index_version:
            return False
        await run_in_threadpool(self._registry.load, Path(active.path))
        _log.info("index.activated", version=active.version, source="poll")
        return True

    def start_rebuild(self, db: Database, actor: Actor) -> None:
        if self.rebuild_state.running:
            raise RebuildInProgressError
        self.rebuild_state = RebuildState(
            running=True, started_at=utcnow(), history=self.rebuild_state.history
        )
        self._rebuild_task = asyncio.create_task(self._rebuild(db, actor), name="index-rebuild")

    async def wait_for_rebuild(self) -> None:
        if self._rebuild_task is not None:
            await self._rebuild_task

    async def _rebuild(self, db: Database, actor: Actor) -> None:
        state = self.rebuild_state
        try:
            version = await run_in_threadpool(self._build_into_store)
            async with db.session() as session:
                manifest = read_manifest(self._store_dir / version)
                await version_repo.register(
                    session,
                    version=version,
                    path=str(self._store_dir / version),
                    manifest=manifest,
                    source="rebuild",
                )
                audit.record(
                    session,
                    actor,
                    "index.rebuild",
                    target_type="index_version",
                    target_id=version,
                    details={"corpus_dir": str(self._corpus_dir)},
                )
                await session.commit()
            state.last_version = version
            state.history.append(version)
        except Exception as exc:
            _log.exception("index.rebuild_failed")
            state.last_error = f"{type(exc).__name__}: {exc}"
            async with db.session() as session:
                audit.record(
                    session,
                    actor or SYSTEM,
                    "index.rebuild_failed",
                    details={"error": state.last_error},
                )
                await session.commit()
        finally:
            state.running = False
            state.finished_at = utcnow()

    def _build_into_store(self) -> str:
        self._store_dir.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=".build-", dir=self._store_dir))
        try:
            out = tmp / "index"
            self._build(self._corpus_dir, out)
            version = str(read_manifest(out)["index_version"])
            final = self._store_dir / version
            if final.exists():  # identical inputs give an identical build (SC1)
                return version
            out.rename(final)
            return version
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
