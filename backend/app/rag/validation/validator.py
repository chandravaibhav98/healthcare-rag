"""`EvidenceValidator`: implements the `Validator` protocol (ADR-0002).

Signals, all in [0, 1]:
* coverage: answer content tokens found in the cited chunk text (brief D3)
* query_support: IDF-weighted share of the question's key terms found in the BEST single
  cited chunk (synonym-aware; see `support.py`). Phase 4: a real answer usually has one
  passage that covers the whole question, while an off-topic question collects partial
  matches spread over several chunks, so the union over-credits it (AUC 0.952 → 0.983).
* retrieval_score: cosine(expanded question, best cited chunk) in the embedding space
* numeric_ok: every number/unit in the answer appears in the cited evidence

`retrieval_score` is an **absolute** similarity, not the rank-based RRF score. The Phase 3
probe showed that the normalised RRF score of the top hit is ~0.94 even for out-of-scope
questions (RRF only sees ranks), so it cannot detect "the corpus has no answer". The
cosine separated in-scope from out-of-scope questions with an AUC of 0.91.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from app.domain.models import GeneratedAnswer, RetrievedChunk, ValidationResult
from app.rag.pipeline import LoadedIndex
from app.rag.retrieval.expansion import QueryExpander
from app.rag.validation.confidence import ConfidenceWeights, combine
from app.rag.validation.coverage import coverage
from app.rag.validation.numeric import numeric_consistency
from app.rag.validation.support import query_support


class EvidenceValidator:
    def __init__(
        self,
        index: LoadedIndex,
        *,
        expander: QueryExpander | None = None,
        weights: ConfidenceWeights | None = None,
        idf_weighted_support: bool = True,
    ) -> None:
        self._index = index
        self._expander = expander
        self._weights = weights or ConfidenceWeights()
        self._term_weight = index.bm25.idf if idf_weighted_support else None

    def relevance(self, question: str, evidence: Sequence[RetrievedChunk]) -> float:
        """Max cosine between the (expanded) question and the evidence chunks; 0.0 if none."""
        if not evidence:
            return 0.0
        query = self._expander.expand(question).text if self._expander else question
        emb = self._index.embedder
        sims = emb.embed([c.chunk.embed_text for c in evidence]) @ emb.embed([query])[0]
        return round(float(np.clip(sims.max(), 0.0, 1.0)), 6)

    def validate(
        self,
        question: str,
        answer: GeneratedAnswer,
        evidence: Sequence[RetrievedChunk],
        *,
        weights: ConfidenceWeights | None = None,
    ) -> ValidationResult:
        """`weights` overrides the construction-time weights (runtime tuning, Phase 5)."""
        if answer.is_empty:
            return ValidationResult(
                coverage=0.0,
                query_support=0.0,
                retrieval_score=self.relevance(question, evidence),
                numeric_ok=True,
                confidence=0.0,
            )
        cited = [c.retrieved for c in answer.citations]
        texts = [c.chunk.text for c in cited]
        headed = [f"{c.chunk.title}\n{c.chunk.section}\n{c.chunk.text}" for c in cited]
        cov = round(coverage(answer.text, texts), 6)
        qs = round(
            max(query_support(question, [h], self._expander, self._term_weight) for h in headed),
            6,
        )
        rs = self.relevance(question, cited)
        numeric = numeric_consistency(answer.text, texts)
        return ValidationResult(
            coverage=cov,
            query_support=qs,
            retrieval_score=rs,
            numeric_ok=numeric.ok,
            confidence=combine(cov, qs, rs, weights or self._weights),
            unsupported_numbers=numeric.unsupported,
        )
