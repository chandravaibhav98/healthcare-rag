"""DocumentSource seam (RUNBOOK §4): any source goes through the same validation."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.rag.ingestion.loader import CorpusError, load_corpus, load_documents
from app.rag.ingestion.sources import DocumentSource, LocalDirectorySource, SourceFile


class MemorySource:
    """What a gateway/S3/SharePoint adapter looks like to the loader."""

    def __init__(self, files: list[SourceFile]) -> None:
        self._files = files

    @property
    def name(self) -> str:
        return "memory://test"

    def files(self) -> Iterator[SourceFile]:
        yield from self._files


def _snapshot(root: Path) -> list[SourceFile]:
    return list(LocalDirectorySource(root, skip={"README.md", "CORPUS_CARD.md"}).files())


def test_sources_satisfy_the_protocol(fixture_corpus: Path) -> None:
    assert isinstance(LocalDirectorySource(fixture_corpus), DocumentSource)
    assert isinstance(MemorySource([]), DocumentSource)


def test_a_remote_style_source_yields_the_same_documents(fixture_corpus: Path) -> None:
    local = load_corpus(fixture_corpus)
    remote = load_documents(MemorySource(_snapshot(fixture_corpus)))
    assert [(d.path, d.sha256) for d in remote] == [(d.path, d.sha256) for d in local]


def test_unsorted_sources_are_rejected(fixture_corpus: Path) -> None:
    files = list(reversed(_snapshot(fixture_corpus)))
    with pytest.raises(CorpusError, match="sorted path order"):
        load_documents(MemorySource(files))


def test_remote_files_get_the_same_validation(fixture_corpus: Path) -> None:
    first = _snapshot(fixture_corpus)[0]
    misplaced = SourceFile(path=f"nih/{first.path.split('/')[-1]}", data=first.data)
    with pytest.raises(CorpusError, match="must live in"):
        load_documents(MemorySource([misplaced]))
    with pytest.raises(CorpusError, match="no guideline documents"):
        load_documents(MemorySource([]))
