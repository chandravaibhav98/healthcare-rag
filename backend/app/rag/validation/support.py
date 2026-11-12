"""Query support: does the cited evidence talk about what the question asks?

    query_support = |supported key terms| / |key terms of the question|

A key term is supported if it appears in the evidence, or if the question phrase it
belongs to has a synonym/acronym alternative (ADR-0004 map) that fully appears in the
evidence. Without that, "taking off PPE" would look unsupported by evidence that says
"doffing personal protective equipment" (Phase 3 probe: 0.33 → 1.0).

Terms are weighted by corpus IDF when `term_weight` is given (the runtime passes the BM25
IDF). Without weighting, generic words ("recommended", "dose", "return") can carry an
off-topic question past the threshold while its one specific term ("ibuprofen", "tax")
is missing from the evidence. Out-of-vocabulary terms get the maximum IDF, because a
term the corpus has never seen is the strongest sign the question is out of scope.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from app.rag.analysis import analyze
from app.rag.retrieval.expansion import QueryExpander
from app.rag.validation.tokenize import content_tokens, question_key_terms


def query_support(
    question: str,
    evidence: Iterable[str],
    expander: QueryExpander | None,
    term_weight: Callable[[str], float] | None = None,
) -> float:
    key = question_key_terms(question)
    if not key:
        return 0.0
    evidence_terms: set[str] = set()
    for text in evidence:
        evidence_terms |= content_tokens(text)
    supported = set(key & evidence_terms)
    if expander is not None:
        for group in expander.matched_groups(question):
            alternatives = (frozenset(analyze(" ".join(m))) for m in group.members)
            if any(alt and alt <= evidence_terms for alt in alternatives):
                for phrase in group.matched:
                    supported |= set(analyze(" ".join(phrase))) & key
    if term_weight is None:
        return len(supported) / len(key)
    total = sum(term_weight(t) for t in key)
    if total <= 0.0:
        return len(supported) / len(key)
    return min(1.0, sum(term_weight(t) for t in supported) / total)
