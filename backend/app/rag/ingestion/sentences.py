"""Rule-based sentence splitter that is safe around medical abbreviations and numbers."""

from __future__ import annotations

import re
from typing import Final

ABBREVIATIONS: Final = frozenset(
    {
        "e.g",
        "i.e",
        "etc",
        "approx",
        "fig",
        "figs",
        "vs",
        "dr",
        "no",
        "nos",
        "min",
        "max",
        "incl",
        "dept",
        "ref",
        "al",
        "st",
        "mr",
        "ms",
        "mrs",
        "vol",
        "cf",
        "resp",
        "ca",
    }
)
# Candidate boundary: terminal punctuation, optional closing quote/bracket, whitespace.
_BOUNDARY: Final = re.compile(r"[.!?]+[\"')\]]*\s+")
_PREV_WORD: Final = re.compile(r"([A-Za-z][A-Za-z.]*)\.$")


def split_sentences(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    sentences: list[str] = []
    start = 0
    for m in _BOUNDARY.finditer(text):
        end = m.end()
        candidate = text[start : m.start() + len(m.group(0).rstrip())]
        nxt = text[end : end + 1]
        prev = _PREV_WORD.search(candidate)
        if prev and prev.group(1).lower().rstrip(".") in ABBREVIATIONS:
            continue  # "e.g. gloves" / "approx. 20 s"
        # No "single capital = initial" rule: units such as "°C." end sentences far more
        # often than personal initials do in guideline text.
        if nxt and nxt.islower():
            continue  # sentences do not start lower-case
        sentences.append(candidate.strip())
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of sentences in `text`, using the same rules as `split_sentences`.

    Offsets refer to the original string (whitespace is not collapsed), which lets the UI
    highlight the exact source text of an answer sentence. On single-spaced text,
    ``[text[s:e] for s, e in sentence_spans(text)] == split_sentences(text)``.
    """
    spans: list[tuple[int, int]] = []
    start = len(text) - len(text.lstrip())
    for m in _BOUNDARY.finditer(text):
        end_punct = m.start() + len(m.group(0).rstrip())
        candidate = text[start:end_punct]
        nxt = text[m.end() : m.end() + 1]
        prev = _PREV_WORD.search(candidate)
        if prev and prev.group(1).lower().rstrip(".") in ABBREVIATIONS:
            continue
        if nxt and nxt.islower():
            continue
        if candidate.strip():
            spans.append((start, end_punct))
        start = m.end()
    tail = text[start:].rstrip()
    if tail.strip():
        spans.append((start, start + len(tail)))
    return spans
