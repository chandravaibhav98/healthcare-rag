from __future__ import annotations

import pytest

from app.rag.analysis import analyze, count_tokens, stem, word_tokens
from app.rag.ingestion.normalizer import normalize_text, sha256_text
from app.rag.ingestion.sentences import split_sentences


def test_normalize_makes_crlf_bom_and_nfd_identical() -> None:
    lf = "Café guidance\nline two\n"
    variants = ["﻿Café guidance\r\nline two\r\n", "Café guidance  \nline two\n\n\n"]
    for v in variants:
        assert normalize_text(v) == lf
        assert sha256_text(normalize_text(v)) == sha256_text(lf)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Wear gloves. Remove them after use.", ["Wear gloves.", "Remove them after use."]),
        (
            "Use PPE, e.g. gloves and gowns. Then wash.",
            ["Use PPE, e.g. gloves and gowns.", "Then wash."],
        ),
        ("Rub for approx. 20 s. Dry hands.", ["Rub for approx. 20 s.", "Dry hands."]),
        ("Store at 2.5 °C. Check daily.", ["Store at 2.5 °C.", "Check daily."]),
        ("See Fig. 2 for steps. Done.", ["See Fig. 2 for steps.", "Done."]),
        ("Ask Dr. Smith. He knows.", ["Ask Dr. Smith.", "He knows."]),
        ("Is it safe? Yes!", ["Is it safe?", "Yes!"]),
        ("", []),
    ],
)
def test_sentence_splitter(text: str, expected: list[str]) -> None:
    assert split_sentences(text) == expected


def test_word_tokens_keep_numbers_and_units_atomic() -> None:
    assert word_tokens("Store at 2-8 °C; COVID-19 dose 0.5 mL") == [
        "store",
        "at",
        "2-8",
        "c",
        "covid-19",
        "dose",
        "0.5",
        "ml",
    ]


def test_analyze_removes_stopwords_and_stems() -> None:
    assert analyze("The vaccines are stored in refrigerators") == ["vaccin", "store", "refriger"]


def test_numbers_are_never_stemmed() -> None:
    assert stem("2-8") == "2-8"


def test_count_tokens_counts_symbols() -> None:
    # Rub 20 – 30 s ( 70 % alcohol ) .
    assert count_tokens("Rub 20–30 s (70% alcohol).") == 11
