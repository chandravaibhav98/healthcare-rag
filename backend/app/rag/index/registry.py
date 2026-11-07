"""`IndexRegistry`: owns the active index and swaps it atomically (plan §4 Phase 2).

Readers call `current()` once per request and keep the returned immutable `RagRuntime`
for the whole request. `load()` builds the new runtime *outside* the lock (verification
can take seconds) and then replaces a single reference, so in-flight requests finish on
the old index and new requests see the new one. A request never mixes the two.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from app.rag.index.manifest import read_manifest
from app.rag.pipeline import LoadedIndex, load_index
from app.rag.runtime import RagRuntime

RuntimeFactory = Callable[[LoadedIndex], RagRuntime]


class IndexNotLoadedError(RuntimeError):
    """No index has been loaded yet (the readiness probe reports this in Phase 3)."""


class IndexRegistry:
    def __init__(self, factory: RuntimeFactory) -> None:
        self._factory = factory
        self._lock = threading.Lock()
        self._current: RagRuntime | None = None

    @property
    def is_loaded(self) -> bool:
        return self._current is not None

    def current(self) -> RagRuntime:
        runtime = self._current  # a single reference read is atomic in CPython
        if runtime is None:
            raise IndexNotLoadedError("no index loaded")
        return runtime

    def load(self, index_dir: Path) -> RagRuntime:
        """Verify, load and activate an index. On failure the previous index stays active."""
        runtime = self._factory(load_index(index_dir))
        with self._lock:
            self._current = runtime
        return runtime

    def reload_if_changed(self, index_dir: Path) -> bool:
        """Activate `index_dir` only if its manifest names a different index_version."""
        version = read_manifest(index_dir)["index_version"]
        current = self._current
        if current is not None and current.index_version == version:
            return False
        self.load(index_dir)
        return True
