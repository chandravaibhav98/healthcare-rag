"""Hybrid retrieval with Reciprocal Rank Fusion (ADR-0004).

    rrf(d) = Σ_r w_r / (k + rank_r(d))        rank is 1-based; k = RRF_K (60)
    score  = rrf(d) / (Σ_r w_r / (k + 1)) ∈ (0, 1]   (1.0 = ranked first everywhere)

Votes come from RRF_WEIGHT_DENSE / RRF_WEIGHT_SPARSE (tuned on the dev split in
Phase 4) and apply to `hybrid` mode only. `dense` and `sparse` are single-retriever
ablations: they always run their retriever with a full vote, so a tuned dense weight
of 0 never disables an explicit `--mode dense`.

Expansion reaches the retrievers differently. Dense search embeds the expanded text.
Sparse search scores each synonym group as one concept (`sparse.build_clauses`), so a
long expansion such as IPC → "infection prevention and control" cannot outvote the
other concepts in the question.

RRF uses ranks only, so the dense (cosine) and sparse (BM25) score scales never need
calibrating against each other. Ties are broken by `chunk_id`, which makes results
identical on every platform even when BLAS returns scores that differ in the last ulp.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from app.api.schemas.qa import TOP_K_MAX, TOP_K_MIN
from app.domain.models import ExpandedQuery, RetrievedChunk
from app.rag.pipeline import LoadedIndex
from app.rag.retrieval.dense import DenseRetriever
from app.rag.retrieval.expansion import QueryExpander
from app.rag.retrieval.sparse import SparseRetriever


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[int]], k: int, weights: Sequence[float] | None = None
) -> dict[int, float]:
    """Σ over rankings of w / (k + rank), with 1-based ranks. Pure function (unit-tested)."""
    weights = [1.0] * len(rankings) if weights is None else list(weights)
    if len(weights) != len(rankings):
        raise ValueError("one weight per ranking is required")
    fused: dict[int, float] = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        if weight == 0.0:
            continue
        for rank, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + weight / (k + rank)
    return fused


class RetrievalMode(StrEnum):
    HYBRID = "hybrid"
    DENSE = "dense"
    SPARSE = "sparse"


def mode_weights(
    mode: RetrievalMode, dense_weight: float, sparse_weight: float
) -> tuple[float, float]:
    """(dense, sparse) votes actually used. Tuned weights only shape `hybrid`."""
    if mode is RetrievalMode.DENSE:
        return (1.0, 0.0)
    if mode is RetrievalMode.SPARSE:
        return (0.0, 1.0)
    return (dense_weight, sparse_weight)


class HybridRetriever:
    def __init__(
        self,
        index: LoadedIndex,
        *,
        rrf_k: int = 60,
        candidate_k: int = 50,
        expander: QueryExpander | None = None,
        mode: RetrievalMode = RetrievalMode.HYBRID,
        dense_weight: float = 1.0,
        sparse_weight: float = 1.0,
    ) -> None:
        if rrf_k < 1 or candidate_k < 1:
            raise ValueError("rrf_k and candidate_k must be >= 1")
        if dense_weight < 0 or sparse_weight < 0 or dense_weight + sparse_weight == 0:
            raise ValueError("RRF weights must be >= 0 and not both 0")
        self._index = index
        self._dense = DenseRetriever(index)
        self._sparse = SparseRetriever(index, expander)
        self._rrf_k = rrf_k
        self._candidate_k = candidate_k
        self._expander = expander
        self._mode = mode
        self._weights = mode_weights(mode, dense_weight, sparse_weight)

    @property
    def weights(self) -> tuple[float, float]:
        """(dense, sparse) votes in effect for this retriever's mode."""
        return self._weights

    def expand(self, question: str) -> ExpandedQuery:
        return self._expander.expand(question) if self._expander else ExpandedQuery(question, ())

    def retrieve(self, question: str, top_k: int) -> list[RetrievedChunk]:
        if not TOP_K_MIN <= top_k <= TOP_K_MAX:
            raise ValueError(f"top_k must be in [{TOP_K_MIN}, {TOP_K_MAX}], got {top_k}")
        if not question.strip():
            raise ValueError("question must not be empty")

        depth = max(self._candidate_k, top_k)
        # A retriever with a zero vote is skipped entirely (no wasted search).
        dense = (
            self._dense.search(self.expand(question).text, depth) if self._weights[0] > 0 else []
        )
        sparse = self._sparse.search_question(question, depth) if self._weights[1] > 0 else []
        dense_rank = {row: r for r, (row, _) in enumerate(dense, start=1)}
        sparse_rank = {row: r for r, (row, _) in enumerate(sparse, start=1)}

        k = self._rrf_k
        fused = reciprocal_rank_fusion(
            [[r for r, _ in dense], [r for r, _ in sparse]], k, self._weights
        )
        best_possible = sum(self._weights) / (k + 1)
        chunks = self._index.chunks
        ordered = sorted(fused.items(), key=lambda p: (-round(p[1], 12), chunks[p[0]].chunk_id))
        return [
            RetrievedChunk(
                chunk=chunks[row],
                rank=i,
                score=min(1.0, score / best_possible),
                dense_rank=dense_rank.get(row),
                sparse_rank=sparse_rank.get(row),
            )
            for i, (row, score) in enumerate(ordered[:top_k], start=1)
        ]
