from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.rag.ingestion.loader import CorpusError, load_corpus, split_front_matter

VALID_META = """---
doc_id: who-abc-001
title: T
source_org: WHO
version: "1.0"
effective_date: 2024-01-01
topic: [ppe]
audience: [clinical-staff]
jurisdiction: global
synthetic: true
---

## Section

Body text.
"""


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def test_fixture_corpus_loads_in_sorted_path_order(fixture_corpus: Path) -> None:
    docs = load_corpus(fixture_corpus)
    assert [d.path for d in docs] == ["cdc/cdc-tst-002.md", "who/who-tst-001.md"]
    assert docs[0].meta.supersedes == "who-tst-001"


def test_crlf_checkout_hashes_like_lf(tmp_path: Path) -> None:
    _write(tmp_path / "lf", "who/who-abc-001.md", VALID_META)
    _write(tmp_path / "crlf", "who/who-abc-001.md", VALID_META.replace("\n", "\r\n"))
    lf, crlf = load_corpus(tmp_path / "lf")[0], load_corpus(tmp_path / "crlf")[0]
    assert lf.sha256 == crlf.sha256
    assert lf.body == crlf.body


def test_readme_and_corpus_card_are_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "who/who-abc-001.md", VALID_META)
    _write(tmp_path, "README.md", "# not a guideline")
    _write(tmp_path, "CORPUS_CARD.md", "# card")
    assert len(load_corpus(tmp_path)) == 1


@pytest.mark.parametrize(
    ("rel", "text", "message"),
    [
        ("who/other-name.md", VALID_META, "file name must be"),
        ("cdc/who-abc-001.md", VALID_META, "must live in 'who/'"),
        (
            "who/who-abc-001.md",
            VALID_META.replace("synthetic: true", "synthetic: false"),
            "synthetic",
        ),
        (
            "who/who-abc-001.md",
            VALID_META.replace("source_org: WHO", "source_org: FDA"),
            "source_org",
        ),
        ("who/who-abc-001.md", VALID_META.replace("title: T\n", ""), "title"),
        ("who/who-abc-001.md", VALID_META.replace("---\n", "", 1), "missing YAML front-matter"),
        ("who/who-abc-001.md", VALID_META.split("\n---\n")[0] + "\n", "unterminated"),
        (
            "who/who-abc-001.md",
            VALID_META.replace("## Section\n\nBody text.\n", ""),
            "empty document body",
        ),
    ],
)
def test_invalid_documents_are_rejected(tmp_path: Path, rel: str, text: str, message: str) -> None:
    _write(tmp_path, rel, text)
    with pytest.raises(CorpusError, match=message):
        load_corpus(tmp_path)


def test_supersession_must_be_consistent(tmp_path: Path, fixture_corpus: Path) -> None:
    shutil.copytree(fixture_corpus, tmp_path / "c")
    old = tmp_path / "c" / "who" / "who-tst-001.md"
    old.write_text(
        old.read_text(encoding="utf-8").replace("status: superseded\n", ""), encoding="utf-8"
    )
    with pytest.raises(CorpusError, match="must have status 'superseded'"):
        load_corpus(tmp_path / "c")


def test_orphan_superseded_document_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "who/who-abc-001.md",
        VALID_META.replace("synthetic: true", "status: superseded\nsynthetic: true"),
    )
    with pytest.raises(CorpusError, match="no document supersedes it"):
        load_corpus(tmp_path)


def test_front_matter_must_be_a_mapping() -> None:
    with pytest.raises(CorpusError, match="mapping"):
        split_front_matter("---\n- a\n- b\n---\nbody\n", "x.md")
