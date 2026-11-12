"""One-stop evaluation run (plan Phase 4): retrieval + validation + threshold curve, one
report folder, a printed scorecard against the success criteria, and an optional
regression gate.

    uv run python -m evaluation.run --split dev            # full report
    uv run python -m evaluation.run --split dev --gate     # CI: fail on regression
    uv run python -m evaluation.run --split dev --update-baseline   # after a deliberate change

The gate compares the DEV pool with `evaluation/baseline.json`. Dev is deterministic (same
index, same code → same numbers), so any drop is a real change, not noise. The literal
success criteria are printed but are not the gate: on this corpus SC2's P@5 is capped by
the relevance sets (ADR-0001), so the gate enforces "no regression" plus the safety rule
"no false validations on dev". `--require-targets` adds the literal SC2/SC3 thresholds.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app.core.config import Settings, get_settings
from app.rag.pipeline import LoadedIndex
from evaluation import eval_retrieval, eval_validation
from evaluation.common import git_revision, load_checked_index, load_split, new_run_dir, write_json
from evaluation.eval_retrieval import write_rows
from evaluation.schemas import Split
from evaluation.svg import line_chart
from evaluation.threshold_sweep import BRIEF_TAU, sweep

BASELINE_PATH: Final = Path(__file__).resolve().parent / "baseline.json"
#: Allowed drop before the gate fails (dev is deterministic; this only absorbs rounding).
TOLERANCE: Final = 0.005
SC2_P_AT_5: Final = 0.65
SC3_PASS_RATE: Final = 0.80
MAX_FALSE_VALIDATION: Final = 0.05


def scorecard(retrieval: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    o, a, u = retrieval["overall"], validation["answerable"], validation["unanswerable"]
    return {
        "p@5": o["p@5"]["mean"],
        "p@5_ceiling": o["ceiling@5"]["mean"],
        "p@5_of_ceiling": o["p@5_of_ceiling"],
        "hit@5": o["hit@5"]["mean"],
        "mrr": o["rr"]["mean"],
        "ndcg@5": o["ndcg@5"]["mean"],
        "pass_rate": a["pass_rate"]["mean"],
        "grounded_pass_rate": a["grounded_pass_rate"]["mean"],
        "false_validation_rate": u["false_validation_rate"]["mean"],
        "mean_confidence": a["mean_confidence"],
    }


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    scorecard: dict[str, Any]
    retrieval: dict[str, Any]
    validation: dict[str, Any]
    curve: list[dict[str, float]]
    retrieval_rows: list[dict[str, Any]]
    validation_rows: list[dict[str, Any]]

    def summary(self, settings: Settings, index_version: str, split: Split) -> dict[str, Any]:
        """JSON document stored in reports and in the `eval_runs` table."""
        return {
            "split": split.value,
            "index_version": index_version,
            "git": git_revision(),
            "scorecard": self.scorecard,
            "retrieval": self.retrieval,
            "validation": self.validation,
            "threshold_curve": self.curve,
            "config": {
                "retrieval_mode": self.retrieval["config"]["mode"],
                "rrf_weights": [settings.rrf_weight_dense, settings.rrf_weight_sparse],
                "expansion": self.retrieval["config"]["expansion"],
                "threshold": settings.confidence_threshold,
                "weights": [
                    settings.confidence_weight_coverage,
                    settings.confidence_weight_query_support,
                    settings.confidence_weight_retrieval,
                ],
                "retrieval_floor": settings.retrieval_floor,
                "mmr_lambda": settings.answer_mmr_lambda,
            },
        }


def evaluate_split(index: LoadedIndex, split: Split, settings: Settings) -> EvaluationResult:
    """Run retrieval + validation + threshold curve in-process (no files written).

    Shared by this CLI and the admin API's evaluation runs (Phase 5)."""
    retrieval, ret_rows = eval_retrieval.evaluate(index, split, settings)
    val_rows = eval_validation.run_service(index, load_split(split), settings)
    validation = eval_validation.summarize(val_rows, settings.confidence_threshold)
    curve = sweep(
        val_rows,
        (
            settings.confidence_weight_coverage,
            settings.confidence_weight_query_support,
            settings.confidence_weight_retrieval,
        ),
    )
    return EvaluationResult(
        scorecard(retrieval, validation), retrieval, validation, curve, ret_rows, val_rows
    )


def check_gate(
    card: dict[str, Any], baseline: dict[str, Any], *, require_targets: bool
) -> list[str]:
    failures = []
    for key in ("p@5", "hit@5", "ndcg@5", "pass_rate", "grounded_pass_rate"):
        if card[key] < baseline[key] - TOLERANCE:
            failures.append(f"{key} regressed: {card[key]:.4f} < baseline {baseline[key]:.4f}")
    if card["false_validation_rate"] > baseline["false_validation_rate"]:
        failures.append(f"false validations increased: {card['false_validation_rate']:.4f}")
    if card["false_validation_rate"] > MAX_FALSE_VALIDATION:
        failures.append(
            f"false-validation rate {card['false_validation_rate']:.4f} > {MAX_FALSE_VALIDATION}"
        )
    if require_targets:
        if card["p@5"] < SC2_P_AT_5:
            failures.append(f"SC2: P@5 {card['p@5']:.4f} < {SC2_P_AT_5}")
        if card["pass_rate"] < SC3_PASS_RATE:
            failures.append(f"SC3: pass rate {card['pass_rate']:.4f} < {SC3_PASS_RATE}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Full evaluation run with scorecard and gate.")
    parser.add_argument("--split", choices=[s.value for s in Split], default="dev")
    parser.add_argument(
        "--gate", action="store_true", help="fail on regression vs baseline.json (dev)"
    )
    parser.add_argument(
        "--require-targets", action="store_true", help="also require SC2/SC3 literally"
    )
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--index", type=Path, default=None)
    args = parser.parse_args(argv)
    if (args.gate or args.update_baseline) and args.split != Split.DEV.value:
        parser.error(
            "the baseline and the gate use the dev pool; run the test split once per frozen config"
        )

    settings = get_settings()
    index = load_checked_index(settings, args.index)
    split = Split(args.split)
    result = evaluate_split(index, split, settings)
    card, curve = result.scorecard, result.curve
    ret_rows, val_rows = result.retrieval_rows, result.validation_rows

    run_dir = new_run_dir("eval", split, index.index_version)
    write_json(run_dir / "summary.json", result.summary(settings, index.index_version, split))
    write_rows(run_dir / "retrieval_per_query.csv", ret_rows)
    write_rows(run_dir / "validation_per_query.csv", val_rows)
    write_rows(
        run_dir / "low_confidence.csv",
        eval_validation.review_list(val_rows, settings.confidence_threshold),
    )
    (run_dir / "threshold_sweep.svg").write_text(
        line_chart(
            f"Threshold sweep ({split.value})",
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

    def mark(ok: bool) -> str:
        return "met" if ok else "NOT met"

    print(f"\nEvaluation · {split.value} · index {index.index_version} · {run_dir.name}")
    print(
        f"  SC2  P@5 {card['p@5']:.3f} (target {SC2_P_AT_5}, best possible {card['p@5_ceiling']:.3f}, "
        f"{card['p@5_of_ceiling']:.0%} of it) → {mark(card['p@5'] >= SC2_P_AT_5)}"
    )
    print(f"       Hit@5 {card['hit@5']:.3f} · MRR {card['mrr']:.3f} · nDCG@5 {card['ndcg@5']:.3f}")
    print(
        f"  SC3  pass rate @0.6 {card['pass_rate']:.3f} (target {SC3_PASS_RATE}) → {mark(card['pass_rate'] >= SC3_PASS_RATE)}"
        f" · grounded {card['grounded_pass_rate']:.3f}"
    )
    print(
        f"  Safety  false validations {card['false_validation_rate']:.3f} (limit {MAX_FALSE_VALIDATION})"
    )
    print(f"  Analyst review list: {run_dir / 'low_confidence.csv'}")

    if args.update_baseline:
        write_json(BASELINE_PATH, {"index_version": index.index_version, **card})
        print(f"baseline updated: {BASELINE_PATH.name}")
    if args.gate:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        failures = check_gate(card, baseline, require_targets=args.require_targets)
        if failures:
            print("\nEVALUATION GATE FAILED:\n  - " + "\n  - ".join(failures))
            return 1
        print("\nEvaluation gate passed (no regression vs baseline).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
