from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from app.api.schemas.qa import QAResponse
from app.domain.models import GeneratedAnswer, RetrievedChunk
from app.rag.generation.answer_types import detect_answer_types, matches_answer_type
from app.rag.generation.extractive import ExtractiveGenerator, _candidates, _with_marker
from app.rag.ingestion.sentences import sentence_spans, split_sentences
from app.rag.pipeline import LoadedIndex, load_index
from app.rag.retrieval.expansion import QueryExpander
from app.rag.retrieval.hybrid import HybridRetriever


@pytest.fixture(scope="module")
def index(fixture_index_dir: Path) -> LoadedIndex:
    return load_index(fixture_index_dir)


def _answer(index: LoadedIndex, q: str, **kw: Any) -> tuple[GeneratedAnswer, list[RetrievedChunk]]:
    exp = QueryExpander.from_file()
    hits = HybridRetriever(index, expander=exp).retrieve(q, 5)
    return ExtractiveGenerator(index, expander=exp, **kw).generate(q, hits), hits


# ------------------------------------------------------------ sentence spans ----


@pytest.mark.parametrize(
    "text",
    [
        "Use PPE, e.g. gloves and gowns. Then wash.",
        "Store at 2.5 °C. Check daily. Is it safe? Yes!",
        "  Leading space. And trailing space.  ",
        "No terminal punctuation",
    ],
)
def test_spans_agree_with_split_sentences(text: str) -> None:
    spans = sentence_spans(text)
    assert [text[s:e] for s, e in spans] == split_sentences(text)


def test_spans_on_real_chunks_agree_with_splitter(corpus_index_dir: Path) -> None:
    for chunk in load_index(corpus_index_dir).chunks:
        for para in chunk.text.split("\n"):
            if para and not para.lstrip().startswith(("|", "-", "*")) and not para[0].isdigit():
                assert [para[s:e] for s, e in sentence_spans(para)] == split_sentences(para)


# ----------------------------------------------------------------- candidates ----


def test_candidates_cover_sentences_list_items_and_table_rows() -> None:
    text = (
        "Intro sentence about gloves here. Second sentence about hands here.\n\n"
        "1. Perform hand hygiene for 20 seconds.\n"
        "   Continuation of step one here.\n"
        "2. Put on the gloves carefully now.\n\n"
        "| Item | Value |\n| --- | --- |\n| Storage temperature | 2–8 °C |\n\n"
        "Sub heading:"
    )
    cands = _candidates(0, text)
    texts = [c.text for c in cands]
    assert texts[:2] == ["Intro sentence about gloves here.", "Second sentence about hands here."]
    assert "Perform hand hygiene for 20 seconds. Continuation of step one here." in texts
    assert "Storage temperature: 2–8 °C" in texts
    assert not any(t.startswith(("Item", "---", "Sub heading")) for t in texts)
    for c in cands:  # spans point into the original text
        assert text[c.start : c.end].strip()
    step = next(c for c in cands if c.text.startswith("Perform"))
    assert step.is_list_item
    assert text[step.start : step.end].startswith("1. Perform")


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Wear gloves.", "Wear gloves [3]."),
        ("Is it safe?", "Is it safe [3]?"),
        ("Row: 2 °C", "Row: 2 °C [3]."),
    ],
)
def test_marker_placement(sentence: str, expected: str) -> None:
    assert _with_marker(sentence, 3) == expected


# ---------------------------------------------------------------- answer types ----


@pytest.mark.parametrize(
    ("question", "names"),
    [
        ("How long should hands be rubbed?", {"duration"}),
        ("How often is fit testing repeated?", {"frequency"}),
        ("What temperature should vaccines be stored at?", {"temperature"}),
        ("When must the container be replaced?", {"timing"}),
        ("What is the order for removing PPE?", {"procedure"}),
        ("What is PPE?", set()),
    ],
)
def test_answer_type_detection(question: str, names: set[str]) -> None:
    assert {t.name for t in detect_answer_types(question)} == names


def test_answer_type_matching() -> None:
    types = detect_answer_types("How long should I rub?")
    assert matches_answer_type(types, "The procedure takes 20–30 seconds.", is_list_item=False)
    assert not matches_answer_type(types, "Rub all surfaces of the hands.", is_list_item=False)
    proc = detect_answer_types("What are the steps?")
    assert matches_answer_type(proc, "Don gloves.", is_list_item=True)


# --------------------------------------------------------------------- answers ----


def test_citation_integrity(index: LoadedIndex) -> None:
    answer, _hits = _answer(index, "How often must hand hygiene compliance be monitored?")
    assert not answer.is_empty
    markers = [int(m) for m in re.findall(r"\[(\d+)\]", answer.text)]
    ids = [c.citation_id for c in answer.citations]
    assert ids == list(range(1, len(ids) + 1))
    assert set(markers) == set(ids)  # every marker resolves; every citation is used
    first_use = list(dict.fromkeys(markers))
    assert first_use == ids  # numbered in order of first appearance
    by_id = {c.citation_id: c for c in answer.citations}
    for s in answer.sentences:
        chunk_text = by_id[s.citation_id].retrieved.chunk.text
        assert s.chunk_id == by_id[s.citation_id].retrieved.chunk.chunk_id
        assert " ".join(chunk_text[s.start : s.end].split()).endswith(" ".join(s.text.split()))


def test_answer_respects_max_sentences_and_is_deterministic(index: LoadedIndex) -> None:
    a, _ = _answer(index, "hand hygiene gloves training audit", max_sentences=2)
    b, _ = _answer(index, "hand hygiene gloves training audit", max_sentences=2)
    assert len(a.sentences) <= 2
    assert a == b


def test_superseded_guidance_is_never_answer_text(index: LoadedIndex) -> None:
    answer, hits = _answer(index, "How long is hand hygiene performed with alcohol-based handrub?")
    assert any(h.chunk.superseded for h in hits), "fixture should retrieve the superseded doc"
    assert all(not c.retrieved.chunk.superseded for c in answer.citations)


def test_no_overlap_gives_empty_answer(index: LoadedIndex) -> None:
    answer, _ = _answer(index, "quantum chromodynamics lattice")
    assert answer.is_empty
    assert answer.text == ""


def test_generated_answer_satisfies_api_contract_v1(index: LoadedIndex) -> None:
    """Phase 3 maps GeneratedAnswer to QAResponse; the contract invariants must hold."""
    answer, _ = _answer(index, "Why must gloves be changed between patients?")
    payload = {
        "answer": answer.text,
        "citations": [
            {
                "id": c.citation_id,
                "doc_id": c.retrieved.chunk.doc_id,
                "title": c.retrieved.chunk.title,
                "source_org": c.retrieved.chunk.source_org,
                "section_path": c.retrieved.chunk.section,
                "chunk_id": c.retrieved.chunk.chunk_id,
                "snippet": c.retrieved.chunk.text,
                "score": c.retrieved.score,
            }
            for c in answer.citations
        ],
        "confidence": 0.9,
        "status": "validated",
    }
    QAResponse.model_validate(payload)


def test_invalid_generator_config(index: LoadedIndex) -> None:
    with pytest.raises(ValueError, match="invalid generator"):
        ExtractiveGenerator(index, max_sentences=0)
