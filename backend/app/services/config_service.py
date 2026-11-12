"""Runtime configuration: read, audited update, and the cross-pod poller.

Each pod keeps the active `Tuning` in memory. An admin update writes app_config version
n+1 and applies it locally at once; other pods notice the new version within
CONFIG_POLL_SECONDS. Updates use optimistic concurrency (`expected_version`), so two
admins cannot silently overwrite each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppConfig
from app.repositories import app_config as config_repo
from app.repositories import audit
from app.repositories.audit import Actor
from app.services.tuning import Tuning, TuningHolder

_log = structlog.get_logger("config")


class ConfigConflictError(Exception):
    def __init__(self, current_version: int) -> None:
        super().__init__(f"configuration changed concurrently (current version {current_version})")
        self.current_version = current_version


@dataclass(frozen=True, slots=True)
class ConfigView:
    version: int
    tuning: Tuning
    row: AppConfig | None


class ConfigService:
    def __init__(self, holder: TuningHolder, defaults: Tuning) -> None:
        self._holder = holder
        self._defaults = defaults

    async def current(self, session: AsyncSession) -> ConfigView:
        row = await config_repo.latest(session)
        if row is None:
            return ConfigView(0, self._defaults, None)
        return ConfigView(row.version, Tuning.from_values(row.values, row.version), row)

    async def update(
        self,
        session: AsyncSession,
        *,
        expected_version: int,
        tuning: Tuning,
        comment: str,
        actor: Actor,
    ) -> ConfigView:
        before = await self.current(session)
        if before.version != expected_version:
            raise ConfigConflictError(before.version)
        new_version = before.version + 1
        values: dict[str, Any] = tuning.to_values()
        row = config_repo.add(
            session, version=new_version, values=values, created_by=actor.id, comment=comment
        )
        audit.record(
            session,
            actor,
            "config.update",
            target_type="app_config",
            target_id=str(new_version),
            details={"before": before.tuning.to_values(), "after": values, "comment": comment},
        )
        await session.commit()  # a concurrent writer of the same version fails on the PK
        applied = Tuning.from_values(values, new_version)
        self._holder.set(applied)
        _log.info("config.applied", version=new_version, source="update")
        return ConfigView(new_version, applied, row)

    async def sync(self, session: AsyncSession) -> bool:
        """Apply the newest stored version if this pod is behind. True if it changed."""
        view = await self.current(session)
        if view.version > self._holder.get().version:
            self._holder.set(view.tuning)
            _log.info("config.applied", version=view.version, source="poll")
            return True
        return False
