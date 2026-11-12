"""Retrieval evaluation (plan Phase 4, SC2): P@K, R@K, nDCG@K, Hit@K, MRR, with the
achievable ceiling and bootstrap 95% CIs, overall and per topic / question kind.

    uv run python -m evaluation.eval_retrieval --split dev
    uv run python -m evaluation.eval_retrieval --split test --mode sparse --no-expansion

Only answerable questions are scored (ADR-0001 §3).
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from app.core.config import Settings, get_settings
from app.rag.pipeline import LoadedIndex
from app.rag.retrieval.hybrid import RetrievalMode
from app.rag.runtime import build_runtime
from evaluation import metrics as m
from evaluation.common import git_revision, load_checked_index, load_split, new_run_dir, write_json
from evaluation.schemas import GoldItem, Split

KS: Final = (1, 3, 5, 10)
RETRIEVE_DEPTH: Final = max(KS)


def score_rankings(
    items: Sequence[GoldItem], rankings: Sequence[Sequence[str]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Aggregate metrics for pre-computed rankings (one list of chunk ids per item)."""
    rows: list[dict[str, Any]] = []
    for item, ranked in zip(items, rankings, strict=True):
        g = item.grades
        row: dict[str, Any] = {
            "id": item.id,
            "topic": item.topic,
            "kind": item.kind.value,
            "n_relevant": len(g),
            "question": item.question,
        }
        for k in KS:
            row[f"p@{k}"] = m.precision_at_k(ranked, g, k)
            row[f"r@{k}"] = m.recall_at_k(ranked, g, k)
        row["ceiling@5"] = m.ceiling_at_k(g, 5)
        row["ndcg@5"] = m.ndcg_at_k(ranked, g, 5)
        row["hit@5"] = m.hit_at_k(ranked, g, 5)
        row["rr"] = m.reciprocal_rank(ranked, g)
        row["top5"] = " ".join(ranked[:5])
        rows.append(row)

    def est(key: str, subset: Sequence[dict[str, Any]] = rows) -> dict[str, float | int]:
        return m.bootstrap([r[key] for r in subset]).as_dict()

    overall: dict[str, Any] = {
        key: est(key)
        for key in [
            *(f"p@{k}" for k in KS),
            *(f"r@{k}" for k in KS),
            "ndcg@5",
            "hit@5",
            "rr",
            "ceiling@5",
        ]
    }
    p5, ceil = overall["p@5"]["mean"], overall["ceiling@5"]["mean"]
    overall["p@5_of_ceiling"] = round(float(p5) / float(ceil), 4) if ceil else None

    breakdown: dict[str, dict[str, Any]] = {"topic": {}, "kind": {}}
    for field in ("topic", "kind"):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            groups[r[field]].append(r)
        for name, subset in sorted(groups.items()):
            breakdown[field][name] = {
                "n": len(subset),
                "p@5": round(sum(r["p@5"] for r in subset) / len(subset), 4),
                "ceiling@5": round(sum(r["ceiling@5"] for r in subset) / len(subset), 4),
                "hit@5": round(sum(r["hit@5"] for r in subset) / len(subset), 4),
                "mrr": round(sum(r["rr"] for r in subset) / len(subset), 4),
            }
    return {"overall": overall, "breakdown": breakdown}, rows


def rank_items(
    index: LoadedIndex,
    items: Sequence[GoldItem],
    settings: Settings,
    *,
    mode: RetrievalMode = RetrievalMode.HYBRID,
    expansion: bool | None = None,
) -> list[list[str]]:
    retriever = build_runtime(index, settings, mode=mode, expansion=expansion).retriever
    return [
        [h.chunk.chunk_id for h in retriever.retrieve(i.question, RETRIEVE_DEPTH)] for i in items
    ]


def evaluate(
    index: LoadedIndex,
    split: Split,
    settings: Settings,
    *,
    mode: RetrievalMode = RetrievalMode.HYBRID,
    expansion: bool | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    items = [g for g in load_split(split) if g.answerable]
    rankings = rank_items(index, items, settings, mode=mode, expansion=expansion)
    summary, rows = score_rankings(items, rankings)
    use_expansion = settings.query_expansion_enabled if expansion is None else expansion
    summary["config"] = {
        "split": split.value,
        "mode": mode.value,
        "expansion": use_expansion,
        "index_version": index.index_version,
        "rrf_k": settings.rrf_k,
        "candidate_k": settings.retrieval_candidate_k,
        "git": git_revision(),
    }
    return summary, rows


def write_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieval metrics on a gold split.")
    parser.add_argument("--split", choices=[s.value for s in Split], default="dev")
    parser.add_argument("--mode", choices=[x.value for x in RetrievalMode], default="hybrid")
    parser.add_argument("--no-expansion", action="store_true")
    parser.add_argument("--index", type=Path, default=None)
    args = parser.parse_args(argv)
    settings = get_settings()
    index = load_checked_index(settings, args.index)
    summary, rows = evaluate(
        index,
        Split(args.split),
        settings,
        mode=RetrievalMode(args.mode),
        expansion=False if args.no_expansion else None,
    )
    tag = args.mode + ("-noexp" if args.no_expansion else "")
    run_dir = new_run_dir("retrieval", args.split, index.index_version, tag)
    write_json(run_dir / "metrics.json", summary)
    write_rows(run_dir / "per_query.csv", rows)
    o = summary["overall"]
    print(
        f"{args.split} · {args.mode} · expansion={summary['config']['expansion']} · n={o['p@5']['n']}"
    )
    for key in ("p@5", "ceiling@5", "hit@5", "rr", "ndcg@5", "r@10"):
        e = o[key]
        print(f"  {key:<10} {e['mean']:.3f}  [{e['ci95_low']:.3f}, {e['ci95_high']:.3f}]")
    print(f"  P@5 / ceiling = {o['p@5_of_ceiling']}")
    print(f"report: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
