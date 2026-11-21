"""Where guideline documents come from (RUNBOOK §4, "Swapping in a real repository").

The indexing pipeline only needs an ordered stream of `(path, bytes)` pairs. Keeping that
behind a small protocol is what lets the synthetic `corpus/` folder be replaced by the
organisation's secure guideline repository without touching parsing, chunking, hashing
or validation:

    LocalDirectorySource   the repository's corpus/ (default, used by every script)
    <GatewaySource>        to be written for the target system: an internal document
                           gateway, S3/Azure Blob, SharePoint. See RUNBOOK §4.2 for the
                           contract (sorted paths, raw bytes, no network in the index
                           build step, credentials from workload identity).

Determinism (SC1) is the source's responsibility as far as ordering goes: `files()` must
yield in ascending path order (the loader checks), and two calls over the same content
must yield the same bytes. Snapshot remote content to a local directory, or pin it by
version, before building an index.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SourceFile:
    """One guideline file: corpus-relative POSIX path (`<org>/<doc_id>.md`) and raw bytes."""

    path: str
    data: bytes


@runtime_checkable
class DocumentSource(Protocol):
    """An ordered, repeatable supply of guideline files."""

    @property
    def name(self) -> str:
        """Human-readable origin for error messages and logs (never a credential)."""
        ...

    def files(self) -> Iterable[SourceFile]:
        """Every guideline file, in ascending `path` order."""
        ...


class LocalDirectorySource:
    """Markdown files under a local directory (the repository's `corpus/`)."""

    def __init__(self, root: Path, *, skip: Iterable[str] = ()) -> None:
        self._root = root
        self._skip = frozenset(skip)

    @property
    def name(self) -> str:
        return str(self._root)

    def files(self) -> Iterator[SourceFile]:
        paths = sorted(
            (p for p in self._root.rglob("*.md") if p.name not in self._skip),
            key=lambda p: p.relative_to(self._root).as_posix(),
        )
        for p in paths:
            yield SourceFile(path=p.relative_to(self._root).as_posix(), data=p.read_bytes())
