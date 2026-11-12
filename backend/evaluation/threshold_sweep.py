"""Threshold sweep and (optional) confidence-weight search (plan Phase 4, ADR-0002).

    uv run python -m evaluation.threshold_sweep --split dev
    uv run python -m evaluation.threshold_sweep --split dev --search-weights

The pipeline runs once; every τ and weight combination is then re-scored offline from the
stored signals, which is exact because confidence is a weighted sum of them.

Selection rule (fixed before looking at test): maximise the answerable pass rate subject to
a false-validation rate ≤ 5% on unanswerable questions; ties go to the τ closest to 0.6
(the brief's default) and then to the weights closest to the defaults. Use on dev only.

Weight search constraints come from the brief, not from the data:
* SC3 is defined *at* τ = 0.6, so the weight search keeps τ = 0.6 (`--search-tau`);
* validation must stay coverage-based (D3), so coverage keeps a weight ≥ 0.2
  (`--min-coverage-weight`). Unconstrained, the search drops coverage entirely, because it
  is ≈ 1.0 for every extractive answer and so carries no information.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from app.core.config import get_settings
from evaluation.common import git_revision, load_checked_index, load_split, new_run_dir, write_json
from evaluation.eval_retrieval import write_rows
from evaluation.eval_validation import run_service
from evaluation.schemas import Split
from evaluation.svg import line_chart

TAUS: Final = [round(0.30 + 0.05 * i, 2) for i in range(13)]  # 0.30 … 0.90
MAX_FALSE_VALIDATION: Final = 0.05
BRIEF_TAU: Final = 0.6

Weights = tuple[float, float, float]


def rescore(rows: Sequence[dict[str, Any]], w: Weights, tau: float) -> tuple[float, float]:
    """(pass rate on answerable, false-validation rate on unanswerable) for weights w and τ."""
    passed = fv = n_a = n_u = 0
    for r in rows:
        if r["reason"] in {"no_evidence", "below_retrieval_floor", "numeric_mismatch"}:
            ok = False
        else:
            conf = round(
                w[0] * r["coverage"] + w[1] * r["query_support"] + w[2] * r["retrieval_score"], 6
            )
            ok = conf >= tau
        if r["answerable"]:
            n_a += 1
            passed += ok
        else:
            n_u += 1
            fv += ok
    return passed / max(n_a, 1), fv / max(n_u, 1)


def sweep(rows: Sequence[dict[str, Any]], w: Weights) -> list[dict[str, float]]:
    out = []
    for tau in TAUS:
        p, f = rescore(rows, w, tau)
        out.append(
            {"threshold": tau, "pass_rate": round(p, 4), "false_validation_rate": round(f, 4)}
        )
    return out


def choose(curve: Sequence[dict[str, float]]) -> dict[str, float] | None:
    ok = [c for c in curve if c["false_validation_rate"] <= MAX_FALSE_VALIDATION]
    if not ok:
        return None
    return max(ok, key=lambda c: (c["pass_rate"], -abs(c["threshold"] - BRIEF_TAU)))


def weight_grid(step: float = 0.05) -> list[Weights]:
    n = round(1 / step)
    return [
        (round(a * step, 2), round(b * step, 2), round((n - a - b) * step, 2))
        for a in range(n + 1)
        for b in range(n + 1 - a)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep τ (and optionally the weights).")
    parser.add_argument("--split", choices=[s.value for s in Split], default="dev")
    parser.add_argument("--search-weights", action="store_true")
    parser.add_argument(
        "--search-tau", type=float, default=BRIEF_TAU, help="τ held fixed in the weight search"
    )
    parser.add_argument("--min-coverage-weight", type=float, default=0.2)
    parser.add_argument("--index", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.split == Split.TEST.value and args.search_weights:
        parser.error("weights are tuned on dev only (ADR-0002)")
    settings = get_settings()
    index = load_checked_index(settings, args.index)
    rows = run_service(index, load_split(Split(args.split)), settings)
    current: Weights = (
        settings.confidence_weight_coverage,
        settings.confidence_weight_query_support,
        settings.confidence_weight_retrieval,
    )
    curve = sweep(rows, current)
    result: dict[str, Any] = {
        "split": args.split,
        "index_version": index.index_version,
        "git": git_revision(),
        "weights": current,
        "max_false_validation": MAX_FALSE_VALIDATION,
        "curve": curve,
        "recommended": choose(curve),
    }
    if args.search_weights:
        candidates = []
        for w in weight_grid():
            if w[0] < args.min_coverage_weight:
                continue
            p, f = rescore(rows, w, args.search_tau)
            if f <= MAX_FALSE_VALIDATION:
                dist = sum(abs(a - b) for a, b in zip(w, current, strict=True))
                candidates.append(
                    {
                        "weights": w,
                        "threshold": args.search_tau,
                        "pass_rate": round(p, 4),
                        "false_validation_rate": round(f, 4),
                        "distance_from_current": round(dist, 2),
                    }
                )
        candidates.sort(key=lambda c: (-c["pass_rate"], c["distance_from_current"]))
        result["weight_search"] = {
            "tau": args.search_tau,
            "min_coverage_weight": args.min_coverage_weight,
            "top": candidates[:15],
        }
    run_dir = new_run_dir("sweep", args.split, index.index_version)
    write_json(run_dir / "sweep.json", result)
    write_rows(run_dir / "curve.csv", curve)
    (run_dir / "sweep.svg").write_text(
        line_chart(
            f"Threshold sweep ({args.split}, weights {current})",
            [c["threshold"] for c in curve],
            {
                "pass rate (answerable)": [c["pass_rate"] for c in curve],
                "false validation (unanswerable)": [c["false_validation_rate"] for c in curve],
            },
            x_label="confidence threshold τ",
            y_label="rate",
            markers={"τ=0.6": BRIEF_TAU},
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(f"{args.split} · weights {current}")
    for c in curve:
        print(
            f"  τ={c['threshold']:.2f}  pass={c['pass_rate']:.3f}  false-valid={c['false_validation_rate']:.3f}"
        )
    print(f"recommended: {result['recommended']}")
    for c in result.get("weight_search", {}).get("top", []):
        print(
            f"  w={c['weights']} τ={c['threshold']} pass={c['pass_rate']} fvr={c['false_validation_rate']}"
        )
    print(f"report: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
