"""Prometheus metrics. Each app instance owns its own CollectorRegistry, so tests and
multiple apps in one process never collide on metric names."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

CONFIDENCE_BUCKETS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.15, 0.25, 0.5, 1.0, 2.5)


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        r = self.registry
        self.qa_requests = Counter(
            "qa_requests", "Answered /qa requests by status.", ["status"], registry=r
        )
        self.qa_abstentions = Counter(
            "qa_abstentions", "Abstentions by reason.", ["reason"], registry=r
        )
        self.qa_confidence = Histogram(
            "qa_confidence", "Confidence of /qa answers.", buckets=CONFIDENCE_BUCKETS, registry=r
        )
        self.qa_latency = Histogram(
            "qa_latency_seconds", "QA pipeline latency.", buckets=LATENCY_BUCKETS, registry=r
        )
        self.http_requests = Counter(
            "http_requests", "HTTP requests.", ["method", "route", "status_code"], registry=r
        )
        self.http_latency = Histogram(
            "http_request_duration_seconds",
            "HTTP latency.",
            ["route"],
            buckets=LATENCY_BUCKETS,
            registry=r,
        )
        self.index_info = Gauge(
            "rag_index_info",
            "Active index version (value is always 1).",
            ["index_version"],
            registry=r,
        )

    def observe_qa(
        self, *, status: str, reason: str | None, confidence: float, latency_s: float
    ) -> None:
        self.qa_requests.labels(status=status).inc()
        if reason is not None:
            self.qa_abstentions.labels(reason=reason).inc()
        self.qa_confidence.observe(confidence)
        self.qa_latency.observe(latency_s)

    def observe_http(self, *, method: str, route: str, status_code: int, duration_s: float) -> None:
        self.http_requests.labels(method=method, route=route, status_code=str(status_code)).inc()
        self.http_latency.labels(route=route).observe(duration_s)

    def set_index(self, index_version: str) -> None:
        self.index_info.clear()
        self.index_info.labels(index_version=index_version).set(1)

    def render(self) -> bytes:
        return generate_latest(self.registry)
