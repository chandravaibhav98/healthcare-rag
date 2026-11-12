"""Tiny periodic-task helper for in-process background loops (config poller, retention).

Kept deliberately simple: one asyncio task per loop, errors logged and the loop
continues, cancellation on shutdown. Anything heavier (cross-pod scheduling) belongs to
the platform: a Kubernetes CronJob runs the same retention code via the CLI (Phase 9).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

import structlog

_log = structlog.get_logger("tasks")


class PeriodicTask:
    def __init__(self, name: str, interval_s: float, fn: Callable[[], Awaitable[object]]) -> None:
        self._name = name
        self._interval_s = interval_s
        self._fn = fn
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name=self._name)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def run_once(self) -> None:
        try:
            await self._fn()
        except Exception:  # a failing tick must not kill the loop
            _log.exception("task.failed", task=self._name)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval_s)
            await self.run_once()
