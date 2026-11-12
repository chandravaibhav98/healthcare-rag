"""Read models for the admin dashboard: statistics, corpus inventory, gold export.

Statistics are computed in Python from one windowed query. At the volumes this service
targets (thousands of queries per day) that is simpler and portable across SQLite and
PostgreSQL (percentiles differ per dialect). Past ~1M rows per window, move to SQL
aggregates or a rollup table (noted in the RUNBOOK).
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from statistics import fmean
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Review
from app.rag.pipeline import LoadedIndex
from app.repositories import query_log as query_repo
from app.repositories import reviews as review_repo

TOP_TOPICS = 10


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile (q in [0, 1]); None for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(q * len(ordered))))
    return float(ordered[rank - 1])


@dataclass(frozen=True, slots=True)
class DailyPoint:
    day: date
    total: int
    validated: int
    needs_review: int
    mean_confidence: float | None


@dataclass(frozen=True, slots=True)
class Stats:
    since: datetime
    until: datetime
    total: int
    validated: int
    needs_review: int
    pass_rate: float | None
    abstention_rate: float | None
    mean_confidence: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    reasons: dict[str, int]
    top_topics: list[tuple[str, int]]
    series: list[DailyPoint]


async def stats(session: AsyncSession, since: datetime, until: datetime) -> Stats:
    rows = await query_repo.window_rows(session, since, until)
    total = len(rows)
    validated = sum(1 for r in rows if r.status == "validated")
    confidences = [float(r.confidence) for r in rows]
    latencies = [float(r.latency_ms) for r in rows]
    reasons = Counter(r.reason for r in rows if r.reason)
    topics: Counter[str] = Counter(t for r in rows for t in (r.topics or []))
    by_day: dict[date, list[Any]] = defaultdict(list)
    for r in rows:
        by_day[r.created_at.date()].append(r)
    series = [
        DailyPoint(
            day=day,
            total=len(items),
            validated=sum(1 for r in items if r.status == "validated"),
            needs_review=sum(1 for r in items if r.status == "needs_review"),
            mean_confidence=fmean(float(r.confidence) for r in items),
        )
        for day, items in sorted(by_day.items())
    ]
    return Stats(
        since=since,
        until=until,
        total=total,
        validated=validated,
        needs_review=total - validated,
        pass_rate=validated / total if total else None,
        abstention_rate=(total - validated) / total if total else None,
        mean_confidence=fmean(confidences) if confidences else None,
        latency_p50_ms=percentile(latencies, 0.50),
        latency_p95_ms=percentile(latencies, 0.95),
        reasons=dict(sorted(reasons.items())),
        top_topics=topics.most_common(TOP_TOPICS),
        series=series,
    )


@dataclass(frozen=True, slots=True)
class DocumentInfo:
    doc_id: str
    title: str
    source_org: str
    version: str
    effective_date: str
    status: str
    supersedes: str | None
    topics: list[str]
    path: str
    chunk_count: int
    token_count: int


def documents(index: LoadedIndex) -> list[DocumentInfo]:
    """Corpus inventory of the active index, from its manifest plus chunk counts."""
    chunks: Counter[str] = Counter(c.doc_id for c in index.chunks)
    tokens: Counter[str] = Counter()
    for c in index.chunks:
        tokens[c.doc_id] += c.token_count
    out = []
    for d in index.manifest["corpus"]["documents"]:
        doc_id = str(d["doc_id"])
        out.append(
            DocumentInfo(
                doc_id=doc_id,
                title=str(d.get("title", "")),
                source_org=str(d.get("source_org", "")),
                version=str(d.get("version", "")),
                effective_date=str(d.get("effective_date", "")),
                status=str(d.get("status", "current")),
                supersedes=d.get("supersedes"),
                topics=list(d.get("topic", [])),
                path=str(d["path"]),
                chunk_count=chunks[doc_id],
                token_count=tokens[doc_id],
            )
        )
    return out


def gold_candidate(review: Review) -> dict[str, Any]:
    """One promoted review as a gold-source candidate (gold_source.yaml item format).

    Candidates are NOT gold yet: an annotator adds g1 labels and checks g2 before they
    join gold_source.yaml (DATASET_CARD.md, "Feedback loop").
    * approve → the cited chunks are answer-bearing (g2)
    * correct → the reviewer's corrected citations are g2
    * reject  → g2 = corrected citations if any; with none it is an unanswerable candidate
    """
    q = review.query
    cited = [c.get("chunk_id") for c in (q.citations or []) if c.get("chunk_id")]
    g2 = cited if review.verdict == "approve" else list(review.corrected_citations or [])
    return {
        "q": q.question,
        "kind": "direct" if g2 else "unanswerable",
        "g2": g2,
        "g1": [],
        "kw": [],
        "topic": (q.topics or ["unassigned"])[0],
        "source": {
            "query_id": str(q.id),
            "review_id": str(review.id),
            "verdict": review.verdict,
            "note": review.note,
            "index_version": q.index_version,
            "redactions": q.redactions,
        },
    }


async def export_gold_jsonl(session: AsyncSession) -> str:
    """Promoted reviews as JSONL (deterministic order: oldest review first)."""
    lines = [
        json.dumps(gold_candidate(r), ensure_ascii=False, sort_keys=True)
        for r in await review_repo.promoted(session)
    ]
    return "".join(f"{line}\n" for line in lines)
