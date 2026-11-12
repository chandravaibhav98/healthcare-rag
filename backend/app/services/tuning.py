"""Runtime-tunable decision parameters (plan Phase 5: "runtime-tunable with audit").

`QAService` reads one immutable `Tuning` snapshot per request from a `TuningHolder`.
An admin `PUT /admin/config` (or the config poller, for other pods) swaps the snapshot
atomically, so a request never mixes old and new values.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.rag.validation.confidence import ConfidenceWeights


@dataclass(frozen=True, slots=True)
class Tuning:
    threshold: float
    retrieval_floor: float
    # None = use the weights the runtime's validator was built with (fixed-value callers).
    weights: ConfidenceWeights | None = None
    version: int = 0  # app_config version; 0 = environment defaults, never persisted

    @classmethod
    def from_settings(cls, s: Settings) -> Tuning:
        return cls(
            threshold=s.confidence_threshold,
            retrieval_floor=s.retrieval_floor,
            weights=ConfidenceWeights(
                coverage=s.confidence_weight_coverage,
                query_support=s.confidence_weight_query_support,
                retrieval=s.confidence_weight_retrieval,
            ),
        )

    def to_values(self) -> dict[str, Any]:
        w = self.weights or ConfidenceWeights()
        return {
            "threshold": self.threshold,
            "retrieval_floor": self.retrieval_floor,
            "weights": {
                "coverage": w.coverage,
                "query_support": w.query_support,
                "retrieval": w.retrieval,
            },
        }

    @classmethod
    def from_values(cls, values: dict[str, Any], version: int) -> Tuning:
        w = values["weights"]
        return cls(
            threshold=float(values["threshold"]),
            retrieval_floor=float(values["retrieval_floor"]),
            weights=ConfidenceWeights(
                coverage=float(w["coverage"]),
                query_support=float(w["query_support"]),
                retrieval=float(w["retrieval"]),
            ),
            version=version,
        )


class TuningHolder:
    def __init__(self, initial: Tuning) -> None:
        self._lock = threading.Lock()
        self._current = initial

    def get(self) -> Tuning:
        return self._current  # single reference read: atomic

    def set(self, tuning: Tuning) -> None:
        with self._lock:
            self._current = tuning
