"""Wiring: build the query-side runtime (retriever + generator) for a loaded index.

Kept separate from the API so the CLI, evaluation scripts (Phase 4) and the service
(Phase 3) all assemble the pipeline in exactly the same way.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import GeneratorKind, Settings
from app.rag.generation.extractive import ExtractiveGenerator
from app.rag.pipeline import LoadedIndex
from app.rag.retrieval.expansion import QueryExpander
from app.rag.retrieval.hybrid import HybridRetriever, RetrievalMode
from app.rag.validation.confidence import ConfidenceWeights
from app.rag.validation.validator import EvidenceValidator


@dataclass(frozen=True, slots=True)
class RagRuntime:
    """Immutable snapshot: a request holds one and never sees a half-swapped index."""

    index: LoadedIndex
    retriever: HybridRetriever
    generator: ExtractiveGenerator
    validator: EvidenceValidator

    @property
    def index_version(self) -> str:
        return self.index.index_version


def build_runtime(
    index: LoadedIndex,
    settings: Settings,
    *,
    mode: RetrievalMode = RetrievalMode.HYBRID,
    expansion: bool | None = None,
) -> RagRuntime:
    if settings.generator is not GeneratorKind.EXTRACTIVE:
        # Optional LLM generator (plan Phase 2): behind the Generator protocol, off by
        # default, not part of the deterministic core. It is tracked in the backlog.
        raise NotImplementedError("GENERATOR=llm is not implemented; use GENERATOR=extractive")
    use_expansion = settings.query_expansion_enabled if expansion is None else expansion
    expander = QueryExpander.from_file() if use_expansion else None
    retriever = HybridRetriever(
        index,
        rrf_k=settings.rrf_k,
        candidate_k=settings.retrieval_candidate_k,
        expander=expander,
        mode=mode,
        dense_weight=settings.rrf_weight_dense,
        sparse_weight=settings.rrf_weight_sparse,
    )
    generator = ExtractiveGenerator(
        index,
        expander=expander,
        max_sentences=settings.answer_max_sentences,
        mmr_lambda=settings.answer_mmr_lambda,
        min_relative_score=settings.answer_min_relative_score,
    )
    validator = EvidenceValidator(
        index,
        expander=expander,
        weights=ConfidenceWeights(
            coverage=settings.confidence_weight_coverage,
            query_support=settings.confidence_weight_query_support,
            retrieval=settings.confidence_weight_retrieval,
        ),
    )
    return RagRuntime(index=index, retriever=retriever, generator=generator, validator=validator)
