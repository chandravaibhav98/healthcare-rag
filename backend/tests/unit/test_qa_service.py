"""`QAService` orchestration on the fixture index (no HTTP)."""

from __future__ import annotations

import re

import pytest

from app.api.schemas.qa import ABSTENTION_MESSAGE, AbstentionReason, QARequest, QAStatus
from app.core.config import Settings
from app.rag.index.registry import IndexNotLoadedError, IndexRegistry
from app.rag.runtime import build_runtime
from app.services.qa_service import CANDIDATE_SOURCES, QAOutcome, QAService

ANSWERABLE = "How long should hand hygiene with alcohol-based handrub take?"
OFF_TOPIC = "What is the recommended dose of the yellow fever vaccine?"


class Recorder:
    def __init__(self) -> None:
        self.outcomes: list[QAOutcome] = []

    def observe(self, outcome: QAOutcome) -> None:
        self.outcomes.append(outcome)


class Exploding:
    def observe(self, outcome: QAOutcome) -> None:
        raise RuntimeError("observer down")


@pytest.fixture
def registry(fixture_registry: IndexRegistry) -> IndexRegistry:
    return fixture_registry


def _service(registry: IndexRegistry, **kwargs: object) -> tuple[QAService, Recorder]:
    recorder = Recorder()
    params: dict[str, object] = {"threshold": 0.6, "retrieval_floor": 0.15}
    params.update(kwargs)
    service = QAService(registry, observers=(Exploding(), recorder), **params)  # type: ignore[arg-type]
    return service, recorder


def test_validated_answer_cites_every_marker(registry: IndexRegistry) -> None:
    service, recorder = _service(registry)
    resp = service.answer(QARequest(question=ANSWERABLE), "req-1")
    assert resp.status is QAStatus.VALIDATED
    assert resp.confidence >= 0.6
    markers = {int(m) for m in re.findall(r"\[(\d+)\]", resp.answer)}
    assert markers == {c.id for c in resp.citations}
    assert resp.meta is not None
    assert resp.meta.request_id == "req-1"
    assert not resp.meta.abstained
    # The exploding observer did not stop the recorder or the response.
    assert recorder.outcomes[0].response == resp
    assert recorder.outcomes[0].candidate_answer is None


def test_below_floor_abstains_before_generation(registry: IndexRegistry) -> None:
    service, recorder = _service(registry)
    resp = service.answer(QARequest(question=OFF_TOPIC), "req-2")
    assert resp.status is QAStatus.NEEDS_REVIEW
    assert resp.answer == ABSTENTION_MESSAGE
    assert resp.confidence == 0.0
    assert resp.meta is not None
    assert resp.meta.reason is AbstentionReason.BELOW_RETRIEVAL_FLOOR
    assert 0 < len(resp.citations) <= CANDIDATE_SOURCES
    assert [c.id for c in resp.citations] == list(range(1, len(resp.citations) + 1))
    assert recorder.outcomes[0].candidate_answer is None


def test_low_confidence_keeps_candidate_for_reviewers(registry: IndexRegistry) -> None:
    service, recorder = _service(registry, threshold=0.99)
    resp = service.answer(QARequest(question=ANSWERABLE), "req-3")
    assert resp.status is QAStatus.NEEDS_REVIEW
    assert resp.meta is not None
    assert resp.meta.reason is AbstentionReason.LOW_CONFIDENCE
    assert resp.answer == ABSTENTION_MESSAGE
    assert 0.0 < resp.confidence < 0.99  # the real score is reported, not zeroed
    candidate = recorder.outcomes[0].candidate_answer
    assert candidate is not None
    assert candidate not in resp.model_dump_json()  # withheld from the user (ADR-0007)


def test_unloaded_registry_raises() -> None:
    settings = Settings(_env_file=None)
    service = QAService(
        IndexRegistry(lambda index: build_runtime(index, settings)),
        threshold=0.6,
        retrieval_floor=0.15,
    )
    with pytest.raises(IndexNotLoadedError):
        service.answer(QARequest(question=ANSWERABLE), "req-4")


def test_latency_uses_injected_clock(registry: IndexRegistry) -> None:
    ticks = iter([10.0, 10.25])
    service, _ = _service(registry, clock=lambda: next(ticks))
    resp = service.answer(QARequest(question=ANSWERABLE), "req-5")
    assert resp.meta is not None
    assert resp.meta.latency_ms == 250.0
