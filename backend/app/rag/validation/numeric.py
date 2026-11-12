"""Numeric consistency gate (ADR-0002): a healthcare-specific safety check.

Every number (with its unit) in the answer must appear in the cited evidence. Extractive
answers satisfy this by construction. The gate exists so that any future generator
(e.g. the optional LLM generator) can never introduce a dose, interval or temperature
that the sources do not contain.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.rag.validation.tokenize import numeric_tokens


@dataclass(frozen=True, slots=True)
class NumericCheck:
    ok: bool
    unsupported: tuple[str, ...]  # canonical numeric tokens missing from the evidence


def numeric_consistency(answer: str, evidence: Iterable[str]) -> NumericCheck:
    in_answer = numeric_tokens(answer)
    if not in_answer:
        return NumericCheck(ok=True, unsupported=())
    in_evidence: set[str] = set()
    for text in evidence:
        in_evidence |= numeric_tokens(text)
    missing = tuple(sorted(in_answer - in_evidence))
    return NumericCheck(ok=not missing, unsupported=missing)
