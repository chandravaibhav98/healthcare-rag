from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from app.domain.ids import CHUNK_ID_PATTERN
from app.domain.models import Document, FrontMatter
from app.rag.ingestion.chunker import ChunkingConfig, chunk_document, slugify
from app.rag.ingestion.loader import load_corpus

SMALL = ChunkingConfig(min_tokens=60, max_tokens=120, overlap_ratio=0.25)


def _doc(body: str) -> Document:
    meta = FrontMatter(
        doc_id="who-abc-001",
        title="Test",
        source_org="WHO",  # type: ignore[arg-type]
        version="1.0",
        effective_date=date(2024, 1, 1),
        topic=["ppe"],
        audience=["clinical-staff"],
        jurisdiction="global",
        synthetic=True,
    )
    return Document(meta=meta, body=body, path="who/who-abc-001.md", sha256="0" * 64)


def _sentences(n: int, word: str = "gloves") -> str:
    return " ".join(
        f"Sentence number {i} explains why staff change {word} between patients." for i in range(n)
    )


def test_h2_is_a_hard_boundary() -> None:
    chunks = chunk_document(
        _doc(f"## Alpha\n\n{_sentences(1)}\n\n## Beta\n\n{_sentences(1)}\n"), SMALL
    )
    assert [c.section_path for c in chunks] == [("Alpha",), ("Beta",)]


def test_h3_is_soft_until_min_tokens_reached() -> None:
    short = chunk_document(_doc(f"## A\n\n{_sentences(1)}\n\n### Sub\n\n{_sentences(1)}\n"), SMALL)
    assert len(short) == 1
    assert "Sub:" in short[0].text  # heading kept inline
    long = chunk_document(_doc(f"## A\n\n{_sentences(7)}\n\n### Sub\n\n{_sentences(3)}\n"), SMALL)
    assert long[-1].section_path == ("A", "Sub")


def test_tiny_h3_tail_is_merged_but_keeps_its_heading() -> None:
    chunks = chunk_document(_doc(f"## A\n\n{_sentences(7)}\n\n### Sub\n\n{_sentences(1)}\n"), SMALL)
    assert len(chunks) == 1
    assert "Sub:" in chunks[0].text


def test_long_sections_split_with_sentence_overlap() -> None:
    chunks = chunk_document(_doc(f"## A\n\n{_sentences(20)}\n"), SMALL)
    assert len(chunks) > 1
    assert all(c.token_count <= SMALL.max_tokens for c in chunks)
    assert chunks[1].has_overlap
    first_sentence_of_next = chunks[1].text.split(". ")[0] + "."
    assert first_sentence_of_next in chunks[0].text, "overlap must repeat the previous chunk's tail"
    overlap_tokens = sum(len(s.split()) for s in [first_sentence_of_next])
    assert overlap_tokens <= SMALL.overlap_budget


def test_numbered_steps_and_tables_are_never_split() -> None:
    steps = "\n".join(
        f"{i}. Step {i} with a fairly long instruction about donning gloves safely."
        for i in range(1, 16)
    )
    table = "| A | B |\n| --- | --- |\n" + "\n".join(f"| row {i} | value {i} |" for i in range(30))
    chunks = chunk_document(_doc(f"## P\n\n{steps}\n\n{table}\n"), SMALL)
    for c in chunks:
        for line in c.text.split("\n"):
            if re.match(r"^\d+\.", line):
                assert line.endswith("safely."), "a numbered step was split"
    tables = [c for c in chunks if "| A | B |" in c.text]
    assert len(tables) == 1
    assert "| row 29 | value 29 |" in tables[0].text


def test_list_continuation_lines_stay_with_their_item(fixture_corpus: Path) -> None:
    doc = next(d for d in load_corpus(fixture_corpus) if d.doc_id == "who-tst-001")
    proc = next(c for c in chunk_document(doc) if c.section_path == ("Procedure",))
    assert "3. Don gloves immediately before the task.\n   Continuation line" in proc.text


def test_ids_are_valid_unique_and_ordinal_per_section(fixture_corpus: Path) -> None:
    for doc in load_corpus(fixture_corpus):
        chunks = chunk_document(doc, SMALL)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))
        assert all(re.fullmatch(CHUNK_ID_PATTERN, i) for i in ids)
        for c in chunks:
            assert c.chunk_id.endswith(f"::{c.ordinal:04d}")


def test_chunking_is_deterministic(fixture_corpus: Path) -> None:
    runs = [
        [c.to_record() for d in load_corpus(fixture_corpus) for c in chunk_document(d, SMALL)]
        for _ in range(3)
    ]
    assert runs[0] == runs[1] == runs[2]


def test_embed_text_carries_title_and_section() -> None:
    chunk = chunk_document(_doc(f"## Gloves\n\n{_sentences(1)}\n"), SMALL)[0]
    assert chunk.embed_text.startswith("Test\nGloves\n")


def test_duplicate_section_titles_get_distinct_slugs() -> None:
    body = f"## A\n\n### Steps\n\n{_sentences(6)}\n\n## B\n\n### Steps\n\n{_sentences(6)}\n"
    slugs = {c.section_slug for c in chunk_document(_doc(body), SMALL)}
    assert {"a-steps", "b-steps"} <= slugs


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        ("PPE › Gloves", "ppe-gloves"),
        ("  Cold-chain: 2–8 °C!  ", "cold-chain-2-8-c"),
        ("***", "section"),
    ],
)
def test_slugify(text: str, slug: str) -> None:
    assert slugify(text) == slug


def test_invalid_config_is_rejected() -> None:
    with pytest.raises(ValueError, match="min_tokens"):
        ChunkingConfig(min_tokens=400, max_tokens=300)
