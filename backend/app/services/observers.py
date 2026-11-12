"""Observers of completed `/qa` requests: metrics and the query log.

Phase 3 writes the query log as a structured log event. Phase 5 adds a database-backed
observer behind the same `QAObserver` protocol (with PHI redaction before persistence).
"""

from __future__ import annotations

import structlog

from app.core.metrics import Metrics
from app.services.qa_service import QAOutcome


class MetricsObserver:
    def __init__(self, metrics: Metrics) -> None:
        self._m = metrics

    def observe(self, outcome: QAOutcome) -> None:
        r = outcome.response
        self._m.observe_qa(
            status=r.status.value,
            reason=r.meta.reason.value if r.meta and r.meta.reason else None,
            confidence=r.confidence,
            latency_s=outcome.latency_s,
        )


class QueryLogObserver:
    """One `qa.completed` event per request. The question text is logged only when
    LOG_QUESTION_TEXT is true (forbidden in production, ADR-0009)."""

    def __init__(self, *, log_question_text: bool) -> None:
        self._log = structlog.get_logger("qa.query_log")
        self._log_question = log_question_text

    def observe(self, outcome: QAOutcome) -> None:
        r = outcome.response
        meta = r.meta
        event: dict[str, object] = {
            "status": r.status.value,
            "reason": meta.reason.value if meta and meta.reason else None,
            "confidence": r.confidence,
            "top_k": outcome.top_k,
            "latency_ms": round(outcome.latency_s * 1000, 3),
            "index_version": meta.index_version if meta else None,
            "citations": [c.chunk_id for c in r.citations],
            "signals": meta.signals.model_dump() if meta else None,
        }
        if outcome.unsupported_numbers:
            event["unsupported_numbers"] = list(outcome.unsupported_numbers)
        if self._log_question:
            event["question"] = outcome.question
            if outcome.candidate_answer:
                event["candidate_answer"] = outcome.candidate_answer
        self._log.info("qa.completed", **event)
