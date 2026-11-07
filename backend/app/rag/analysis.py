"""Deterministic text analysis shared by indexing (Phase 1) and validation (Phase 3).

Changing anything here changes vectors and BM25 postings, so ANALYSIS_VERSION is
hashed into index_version: bump it on any behavioural change.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from decimal import Decimal, localcontext
from functools import lru_cache
from typing import Final

import snowballstemmer

ANALYSIS_VERSION: Final = 1

# Words keep internal hyphens, apostrophes, dots and commas between alphanumerics, so
# "2-8", "covid-19", "0.5" and "1,000" stay single tokens (atomic numbers, plan Phase 3).
_WORD_RE: Final = re.compile(r"\w+(?:[-'.,]\w+)*")
# Token counting for chunk sizing: words plus standalone symbols (%, °, ›, ...).
_COUNT_RE: Final = re.compile(r"\w+(?:[-'.,]\w+)*|[^\w\s]")

STOPWORDS: Final = frozenset(
    [
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
    ]
)

_local = threading.local()


def _stemmer() -> snowballstemmer.stemmer:
    # Snowball stemmer instances keep internal state: one per thread.
    s = getattr(_local, "stemmer", None)
    if s is None:
        s = snowballstemmer.stemmer("english")
        _local.stemmer = s
    return s


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def word_tokens(text: str) -> list[str]:
    """Lower-cased word tokens in reading order."""
    return [m.group(0) for m in _WORD_RE.finditer(normalize_unicode(text).lower())]


def count_tokens(text: str) -> int:
    """Approximate LLM-style token count used for chunk sizing (no tokenizer download)."""
    return len(_COUNT_RE.findall(text))


@lru_cache(maxsize=65_536)
def stem(word: str) -> str:
    if any(ch.isdigit() for ch in word):
        return word  # numbers and units are atomic: never stemmed
    return str(_stemmer().stemWord(word))


def analyze(text: str) -> list[str]:
    """Content terms: lower-case, stop-words removed, Snowball-stemmed (BM25 and validation)."""
    return [stem(w) for w in word_tokens(text) if w not in STOPWORDS]


@lru_cache(maxsize=4096)
def exact_ln(x: Decimal) -> float:
    """Natural log, correctly rounded in software.

    `math.log` may differ by one ulp between platform C libraries (glibc vs MSVC), which
    could change float32 vectors and break cross-OS byte identity (SC1). Decimal's ln is
    correctly rounded on every platform.
    """
    with localcontext() as ctx:
        ctx.prec = 34
        return float(x.ln())
