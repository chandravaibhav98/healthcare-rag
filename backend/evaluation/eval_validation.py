"""Validation evaluation (plan Phase 4, SC3): runs every gold question through the real
`QAService` and measures what users would see.

Answerable questions (SC3 denominator):
* pass rate          = share returned `validated`                     (SC3: ≥ 0.80 at τ)
* grounded pass rate = validated AND cites ≥ 1 answer-bearing (grade 2) chunk
* keyword recall     = share of `expected_keywords` found in validated answers (diagnostic)
Unanswerable questions:
* abstention recall  = share returned `needs_review`
* false-validation   = share returned `validated`                     (gate: ≤ 0.05)

    uv run python -m evaluation.eval_validation --split dev [--threshold 0.6]
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from app.api.schemas.qa import QARequest, QAStatus
from app.core.config import Settings, get_settings
from app.rag.index.registry import IndexRegistry
from app.rag.pipeline import LoadedIndex
from app.rag.runtime import build_runtime
from app.services.qa_service import QAOutcome, QAService
from app.services.tuning import Tuning, TuningHolder
from evaluation import metrics as m
from evaluation.common import git_revision, load_checked_index, load_split, new_run_dir, write_json
from evaluation.eval_retrieval import write_rows
from evaluation.schemas import GoldItem, Split

#: Answerable items validated with confidence below τ + margin are flagged for analysts.
REVIEW_MARGIN: Final = 0.05
HIST_BINS: Final = [round(0.1 * i, 1) for i in range(11)]


class _Capture:
    def __init__(self) -> None:
        self.last: QAOutcome | None = None

    def observe(self, outcome: QAOutcome) -> None:
        self.last = outcome


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub("[\u2010-\u2015\u2212]", "-", text)  # Unicode dashes and minus → "-"
    return re.sub(r"\s+", " ", text)


def keyword_recall(answer: str, keywords: Sequence[str]) -> float | None:
    if not keywords:
        return None
    body = _norm(answer)
    return sum(_norm(k) in body for k in keywords) / len(keywords)


def run_service(
    index: LoadedIndex, items: Sequence[GoldItem], settings: Settings
) -> list[dict[str, Any]]:
    """One row per gold item with everything needed to re-score offline (sweeps, tuning)."""
    registry = IndexRegistry(lambda idx: build_runtime(idx, settings))
    registry._current = build_runtime(index, settings)
    capture = _Capture()
    service = QAService(
        registry, tuning=TuningHolder(Tuning.from_settings(settings)), observers=(capture,)
    )
    rows: list[dict[str, Any]] = []
    for item in items:
        resp = service.answer(
            QARequest(question=item.question, top_k=settings.retrieval_top_k_default), item.id
        )
        assert resp.meta is not None  # noqa: S101 (always set by QAService)
        assert capture.last is not None  # noqa: S101
        sig = resp.meta.signals
        cited = [c.chunk_id for c in resp.citations]
        answer_text = capture.last.candidate_answer or (
            resp.answer if resp.status is QAStatus.VALIDATED else ""
        )
        rows.append(
            {
                "id": item.id,
                "topic": item.topic,
                "kind": item.kind.value,
                "answerable": item.answerable,
                "status": resp.status.value,
                "reason": resp.meta.reason.value if resp.meta.reason else "",
                "confidence": resp.confidence,
                "coverage": sig.coverage,
                "query_support": sig.query_support,
                "retrieval_score": sig.retrieval_score,
                "numeric_ok": sig.numeric_ok,
                "cites_grade2": any(item.grades.get(c) == 2 for c in cited),
                "keyword_recall": keyword_recall(answer_text, item.expected_keywords),
                "question": item.question,
                "answer": answer_text,
                "citations": " ".join(cited),
            }
        )
    return rows


def status_at(row: dict[str, Any], threshold: float) -> str:
    """Re-decide a row's status for another τ without re-running the pipeline.

    Rows abstained before or regardless of the threshold (no evidence, below the floor,
    numeric mismatch) stay abstained; the rest compare their confidence with τ."""
    if row["reason"] in {"no_evidence", "below_retrieval_floor", "numeric_mismatch"}:
        return "needs_review"
    return "validated" if row["confidence"] >= threshold else "needs_review"


def summarize(rows: Sequence[dict[str, Any]], threshold: float) -> dict[str, Any]:
    ans = [r for r in rows if r["answerable"]]
    una = [r for r in rows if not r["answerable"]]
    passed = [1.0 if status_at(r, threshold) == "validated" else 0.0 for r in ans]
    grounded = [
        1.0 if status_at(r, threshold) == "validated" and r["cites_grade2"] else 0.0 for r in ans
    ]
    false_val = [1.0 if status_at(r, threshold) == "validated" else 0.0 for r in una]
    conf_ans = [r["confidence"] for r in ans]
    kw = [
        r["keyword_recall"]
        for r in ans
        if status_at(r, threshold) == "validated" and r["keyword_recall"] is not None
    ]

    def hist(values: Sequence[float]) -> list[int]:
        counts = [0] * (len(HIST_BINS) - 1)
        for v in values:
            counts[min(int(v * 10), 9)] += 1
        return counts

    by: dict[str, dict[str, Any]] = {"kind": {}, "topic": {}}
    for field in ("kind", "topic"):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in ans:
            groups[r[field]].append(r)
        for name, subset in sorted(groups.items()):
            by[field][name] = {
                "n": len(subset),
                "pass_rate": round(
                    sum(status_at(r, threshold) == "validated" for r in subset) / len(subset), 4
                ),
            }
    return {
        "threshold": threshold,
        "answerable": {
            "pass_rate": m.bootstrap(passed).as_dict(),
            "grounded_pass_rate": m.bootstrap(grounded).as_dict(),
            "mean_confidence": round(statistics.mean(conf_ans), 4) if conf_ans else None,
            "median_confidence": round(statistics.median(conf_ans), 4) if conf_ans else None,
            "keyword_recall_validated": round(statistics.mean(kw), 4) if kw else None,
            "abstention_reasons": dict(
                Counter(
                    r["reason"] or "validated"
                    for r in ans
                    if status_at(r, threshold) != "validated" or not r["reason"]
                )
            ),
            "confidence_histogram": {"bins": HIST_BINS, "counts": hist(conf_ans)},
        },
        "unanswerable": {
            "n": len(una),
            "abstention_recall": round(1 - (sum(false_val) / len(una)), 4) if una else None,
            "false_validation_rate": m.bootstrap(false_val).as_dict(),
            "falsely_validated": [r["id"] for r in una if status_at(r, threshold) == "validated"],
        },
        "breakdown": by,
    }


def review_list(rows: Sequence[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    """Analyst queue: every wrong decision plus validated answers close to τ."""
    out = []
    for r in rows:
        status = status_at(r, threshold)
        if r["answerable"] and status != "validated":
            why = f"abstained ({r['reason'] or 'low_confidence'})"
        elif not r["answerable"] and status == "validated":
            why = "false validation (unanswerable question was answered)"
        elif r["answerable"] and not r["cites_grade2"]:
            why = "validated without an answer-bearing citation"
        elif r["answerable"] and r["confidence"] < threshold + REVIEW_MARGIN:
            why = f"validated within {REVIEW_MARGIN} of the threshold"
        else:
            continue
        out.append(
            {
                "id": r["id"],
                "why": why,
                "confidence": r["confidence"],
                "kind": r["kind"],
                "topic": r["topic"],
                "question": r["question"],
                "answer": r["answer"],
                "citations": r["citations"],
            }
        )
    return sorted(out, key=lambda x: (x["why"], x["confidence"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validation metrics on a gold split.")
    parser.add_argument("--split", choices=[s.value for s in Split], default="dev")
    parser.add_argument(
        "--threshold", type=float, default=None, help="τ (default CONFIDENCE_THRESHOLD)"
    )
    parser.add_argument("--index", type=Path, default=None)
    args = parser.parse_args(argv)
    settings = get_settings()
    tau = settings.confidence_threshold if args.threshold is None else args.threshold
    index = load_checked_index(settings, args.index)
    rows = run_service(index, load_split(Split(args.split)), settings)
    summary = summarize(rows, tau)
    summary["config"] = {
        "split": args.split,
        "index_version": index.index_version,
        "git": git_revision(),
        "weights": [
            settings.confidence_weight_coverage,
            settings.confidence_weight_query_support,
            settings.confidence_weight_retrieval,
        ],
        "retrieval_floor": settings.retrieval_floor,
    }
    run_dir = new_run_dir("validation", args.split, index.index_version)
    write_json(run_dir / "metrics.json", summary)
    write_rows(run_dir / "per_query.csv", rows)
    write_rows(run_dir / "low_confidence.csv", review_list(rows, tau))
    a, u = summary["answerable"], summary["unanswerable"]
    print(f"{args.split} · τ={tau} · answerable n={a['pass_rate']['n']} · unanswerable n={u['n']}")
    print(
        f"  pass rate           {a['pass_rate']['mean']:.3f} [{a['pass_rate']['ci95_low']:.3f}, {a['pass_rate']['ci95_high']:.3f}]"
    )
    print(f"  grounded pass rate  {a['grounded_pass_rate']['mean']:.3f}")
    print(f"  mean confidence     {a['mean_confidence']}  (median {a['median_confidence']})")
    print(f"  keyword recall      {a['keyword_recall_validated']}")
    print(
        f"  false validation    {u['false_validation_rate']['mean']:.3f}  {u['falsely_validated']}"
    )
    print(f"  abstentions         {a['abstention_reasons']}")
    print(f"report: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
