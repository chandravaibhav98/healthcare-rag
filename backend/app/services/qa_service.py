"""`QAService`: the `/qa` use case (plan §2.2).

    retrieve → relevance floor → generate → validate → decide status → respond → observe

Route handlers stay thin: they validate HTTP input and delegate here. This class has no
FastAPI imports, so it can be reused by the evaluation harness (Phase 4) and by tests.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final, Protocol

import structlog

from app.api.schemas.qa import (
    ABSTENTION_MESSAGE,
    AbstentionReason,
    Citation,
    QARequest,
    QAResponse,
    QAStatus,
    ResponseMeta,
    Signals,
)
from app.domain.models import GeneratedAnswer, RetrievedChunk
from app.rag.index.registry import IndexRegistry
from app.rag.validation.confidence import decide

#: Candidate sources returned with an abstention (ADR-0007).
CANDIDATE_SOURCES: Final = 3
_log = structlog.get_logger("qa")


@dataclass(frozen=True, slots=True)
class QAOutcome:
    """Everything observers may need; the API response plus internals not sent to users."""

    request_id: str
    question: str
    top_k: int
    response: QAResponse
    candidate_answer: str | None  # withheld answer text on abstention (reviewers only, ADR-0007)
    unsupported_numbers: tuple[str, ...]
    latency_s: float


class QAObserver(Protocol):
    def observe(self, outcome: QAOutcome) -> None: ...


def _citation(cid: int, hit: RetrievedChunk) -> Citation:
    ch = hit.chunk
    return Citation(
        id=cid,
        doc_id=ch.doc_id,
        title=ch.title,
        source_org=ch.source_org,
        section_path=ch.section,
        chunk_id=ch.chunk_id,
        snippet=ch.text[:2000],
        score=round(hit.score, 6),
        superseded=ch.superseded,
    )


class QAService:
    def __init__(
        self,
        registry: IndexRegistry,
        *,
        threshold: float,
        retrieval_floor: float,
        observers: Sequence[QAObserver] = (),
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._registry = registry
        self._threshold = threshold
        self._floor = retrieval_floor
        self._observers = tuple(observers)
        self._clock = clock

    def answer(self, request: QARequest, request_id: str) -> QAResponse:
        started = self._clock()
        runtime = self._registry.current()  # one immutable snapshot for the whole request
        hits = runtime.retriever.retrieve(request.question, request.top_k)
        relevance = runtime.validator.relevance(request.question, hits)

        generated: GeneratedAnswer | None = None
        reason: AbstentionReason | None
        unsupported: tuple[str, ...]
        if hits and relevance >= self._floor:
            generated = runtime.generator.generate(request.question, hits)

        if generated is None:
            reason = (
                AbstentionReason.NO_EVIDENCE if not hits else AbstentionReason.BELOW_RETRIEVAL_FLOOR
            )
            signals = Signals(
                coverage=0.0, query_support=0.0, retrieval_score=relevance, numeric_ok=True
            )
            status, confidence, unsupported = QAStatus.NEEDS_REVIEW, 0.0, ()
        else:
            result = runtime.validator.validate(request.question, generated, hits)
            status, reason = decide(
                answer_empty=generated.is_empty,
                confidence=result.confidence,
                numeric_ok=result.numeric_ok,
                threshold=self._threshold,
            )
            signals = Signals(
                coverage=result.coverage,
                query_support=result.query_support,
                retrieval_score=result.retrieval_score,
                numeric_ok=result.numeric_ok,
            )
            confidence, unsupported = result.confidence, result.unsupported_numbers

        if status is QAStatus.VALIDATED and generated is not None:
            answer_text = generated.text
            citations = [_citation(c.citation_id, c.retrieved) for c in generated.citations]
            candidate = None
        else:
            # Abstain (ADR-0007): fixed message; still cite the best candidate sources.
            answer_text = ABSTENTION_MESSAGE
            sources = (
                [c.retrieved for c in generated.citations]
                if generated is not None and generated.citations
                else list(hits)
            )
            citations = [
                _citation(i, h) for i, h in enumerate(sources[:CANDIDATE_SOURCES], start=1)
            ]
            candidate = generated.text if generated is not None and generated.text else None

        elapsed = self._clock() - started
        response = QAResponse(
            answer=answer_text,
            citations=citations,
            confidence=confidence,
            status=status,
            meta=ResponseMeta(
                request_id=request_id,
                index_version=runtime.index_version,
                latency_ms=round(elapsed * 1000, 3),
                abstained=status is QAStatus.NEEDS_REVIEW,
                reason=reason,
                signals=signals,
            ),
        )
        self._notify(
            QAOutcome(
                request_id=request_id,
                question=request.question,
                top_k=request.top_k,
                response=response,
                candidate_answer=candidate,
                unsupported_numbers=unsupported,
                latency_s=elapsed,
            )
        )
        return response

    def _notify(self, outcome: QAOutcome) -> None:
        for observer in self._observers:
            try:
                observer.observe(outcome)
            except Exception:  # an observer failure must never fail the user's request
                _log.exception("qa.observer_failed", observer=type(observer).__name__)
