"""Tokenisation for validation (plan §4 Phase 3).

Content tokens reuse the index analyser (NFC, lower-case, stop-words removed, Snowball
stems, numbers atomic), so the validator and BM25 agree on what a "term" is. Numeric
tokens get their own canonical form, so that "20–30 seconds", "20-30 s" and
"20 to 30 sec" compare equal.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

from app.rag.analysis import analyze, word_tokens

_MARKER: Final = re.compile(r"\s*\[\d+\]")
# Answer-type phrases say WHAT KIND of fact is wanted, not what the topic is.
_INTERROGATIVE: Final = re.compile(
    r"\bhow (?:long|often|soon|many|much|quickly|frequently)\b", re.IGNORECASE
)

# en dash, em dash, minus sign, hyphen, non-breaking hyphen → ASCII hyphen-minus
_DASHES: Final = str.maketrans(dict.fromkeys("\u2013\u2014\u2212\u2010\u2011", "-"))
_NUM: Final = r"-?\d+(?:,\d{3})*(?:\.\d+)?"
_UNIT_ALIASES: Final = {
    "%": "%",
    "percent": "%",
    "°c": "°c",
    "° c": "°c",
    "degrees": "°c",
    "°f": "°f",
    "s": "s",
    "sec": "s",
    "secs": "s",
    "second": "s",
    "seconds": "s",
    "min": "min",
    "mins": "min",
    "minute": "min",
    "minutes": "min",
    "h": "h",
    "hr": "h",
    "hrs": "h",
    "hour": "h",
    "hours": "h",
    "day": "day",
    "days": "day",
    "week": "week",
    "weeks": "week",
    "month": "month",
    "months": "month",
    "year": "year",
    "years": "year",
    "ppm": "ppm",
    "mg": "mg",
    "g": "g",
    "kg": "kg",
    "ml": "ml",
    "l": "l",
    "cm": "cm",
    "mm": "mm",
    "m": "m",
    "miu/ml": "miu/ml",
    "iu": "iu",
    "dose": "dose",
    "doses": "dose",
    "ach": "ach",
    "feet": "ft",
    "foot": "ft",
    "inches": "in",
}
_UNIT_RE: Final = "|".join(sorted((re.escape(u) for u in _UNIT_ALIASES), key=len, reverse=True))
_NUMERIC: Final = re.compile(
    # Lookarounds keep numbers inside identifiers ("who-ipc-004", "4.2a") out; an
    # optional hyphen joins compound units ("2-dose series" → "2 dose").
    rf"(?<![\w.\-])(?P<a>{_NUM})(?:\s*(?:-|to)\s*(?P<b>{_NUM}))?"
    rf"(?:\s*-?\s*(?P<u>{_UNIT_RE}))?(?!\w|\.\d)",
    re.IGNORECASE,
)


def strip_citation_markers(text: str) -> str:
    return _MARKER.sub("", text)


def content_tokens(text: str) -> frozenset[str]:
    return frozenset(analyze(strip_citation_markers(text)))


#: Conversational words that carry no topic. They are rare in guideline text, so IDF
#: weighting would otherwise make them look like the most important terms of a lay
#: question ("what happens if…", "what goes into…") and penalise valid paraphrases.
#: Found on the Phase 4 dev split; keep the list short and topic-free.
QUESTION_FILLER: Final = frozenset(
    {
        "get",
        "gets",
        "got",
        "go",
        "goes",
        "going",
        "come",
        "back",
        "happen",
        "happens",
        "happened",
        "do",
        "does",
        "did",
        "done",
        "ever",
        "still",
        "really",
        "exactly",
        "proper",
        "properly",
        "count",
        "counts",
        "kind",
        "thing",
        "things",
        "way",
        "someone",
        "anyone",
        "people",
        "person",
        "need",
        "needs",
        "want",
        "make",
        "makes",
        "made",
        "tell",
        "told",
        "know",
        "ok",
        "okay",
        "allowed",
        "acceptable",
        "safe",
        "far",
        "apart",
        "day",
        "there",
    }
)


def question_key_terms(question: str) -> frozenset[str]:
    """Topical terms of a question: content tokens minus answer-type phrases and filler."""
    words = [w for w in word_tokens(_INTERROGATIVE.sub(" ", question)) if w not in QUESTION_FILLER]
    return frozenset(analyze(" ".join(words)))


def _canonical_number(raw: str) -> str:
    return raw.replace(",", "") if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw) else raw


def numeric_tokens(text: str) -> frozenset[str]:
    """Canonical numbers/ranges with units, e.g. {'20-30 s', '2 °c', '1000 ppm', '70 %'}."""
    norm = unicodedata.normalize("NFKC", strip_citation_markers(text)).translate(_DASHES).lower()
    out: set[str] = set()
    for m in _NUMERIC.finditer(norm):
        value = _canonical_number(m.group("a"))
        if m.group("b"):
            value = f"{value}-{_canonical_number(m.group('b'))}"
        unit = m.group("u")
        out.add(f"{value} {_UNIT_ALIASES[unit.lower()]}" if unit else value)
    return frozenset(out)
