"""Token coverage: the brief's validation signal (D3)."""

from __future__ import annotations

from collections.abc import Iterable

from app.rag.validation.tokenize import content_tokens


def coverage(answer: str, evidence: Iterable[str]) -> float:
    """|C(answer) ∩ C(evidence)| / |C(answer)| over content-token sets; 0.0 for an empty answer.

    Properties (property-tested): the result is in [0, 1]; adding evidence never lowers it;
    an answer copied from its evidence scores 1.0.
    """
    answer_terms = content_tokens(answer)
    if not answer_terms:
        return 0.0
    evidence_terms: set[str] = set()
    for text in evidence:
        evidence_terms |= content_tokens(text)
    return len(answer_terms & evidence_terms) / len(answer_terms)
