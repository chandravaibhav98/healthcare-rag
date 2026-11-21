"""Compare a fresh reproduction with the recorded results and package the submission.

    uv run python scripts/reproduce_report.py --out DIR --dev SUMMARY --test SUMMARY
        [--determinism MANIFEST] [--zip NAME]

Called by scripts/reproduce.{sh,ps1} (plan Phase 12). It checks that:
* the dev scorecard equals `evaluation/baseline.json` (the CI regression baseline);
* the held-out test scorecard equals the archived official result
  (`docs/evaluation/test-v2-results.json`), metric by metric;
* both ran on the index the determinism check built (SC1),
and writes DIR/RESULTS.md: every success criterion with the reproduced value, the target
and whether it is met. With `--zip` it also writes DIR/../NAME.zip and SHA256SUMS.

Exit code 1 when any reproduced number differs from its record. A criterion that is not
met (SC2 as written, the test-v2 false-validation rate) is reported, not an error: the
point is that the numbers are reproducible, including the ones that miss.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[2]
BASELINE: Final = ROOT / "backend/evaluation/baseline.json"
TEST_RECORD: Final = ROOT / "docs/evaluation/test-v2-results.json"
TOLERANCE: Final = 1e-4  # scorecards are rounded to 4 decimals

#: (key, label, target, comparison) for RESULTS.md. None = reported, no target.
CRITERIA: Final = (
    ("p@5", "SC2 Precision@5", 0.65, ">="),
    ("p@5_of_ceiling", "SC2 P@5 as share of the ceiling (ADR-0001 proposal)", None, ""),
    ("hit@5", "Hit@5", None, ""),
    ("ndcg@5", "nDCG@5", None, ""),
    ("pass_rate", "SC3 validation pass rate @ τ 0.6", 0.80, ">="),
    ("false_validation_rate", "False validations (unanswerable questions)", 0.05, "<="),
    ("mean_confidence", "Mean confidence (answerable)", None, ""),
)


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _test_record() -> dict[str, float]:
    """The archived test-v2 result, flattened to scorecard keys."""
    rec = _load(TEST_RECORD)
    r, v = rec["retrieval"], rec["validation"]
    return {
        "index_version": rec["index_version"],
        "p@5": r["p@5"]["mean"],
        "p@5_ceiling": r["ceiling@5"]["mean"],
        "p@5_of_ceiling": r["p@5_of_ceiling"],
        "hit@5": r["hit@5"]["mean"],
        "mrr": r["rr"]["mean"],
        "ndcg@5": r["ndcg@5"]["mean"],
        "pass_rate": v["pass_rate"]["mean"],
        "grounded_pass_rate": v["grounded_pass_rate"]["mean"],
        "false_validation_rate": v["false_validation_rate"]["mean"],
        "mean_confidence": v["mean_confidence"],
    }


def compare(name: str, got: dict[str, Any], want: dict[str, Any]) -> list[str]:
    problems = []
    for key, expected in want.items():
        actual = got.get(key)
        if isinstance(expected, str):
            if actual != expected:
                problems.append(f"{name} {key}: {actual} != recorded {expected}")
        elif actual is None or abs(float(actual) - float(expected)) > TOLERANCE:
            problems.append(f"{name} {key}: {actual} != recorded {expected}")
    return problems


def _met(value: float, target: float | None, op: str) -> str:
    if target is None:
        return "—"
    ok = value >= target if op == ">=" else value <= target
    return "✅ met" if ok else "❌ not met"


def _gate(result: str | None) -> str:
    return {"passed": "✅ passed", "failed": "❌ failed"}.get(result or "", "not run")


def results_md(
    dev: dict[str, Any],
    test: dict[str, Any],
    det: dict[str, Any] | None,
    problems: list[str],
    gates: dict[str, str],
) -> str:
    dev_card, test_card = dev["scorecard"], test["scorecard"]
    lines = [
        "# Reproduction results",
        "",
        f"- Git commit: `{test.get('git', '?')}` · index `{test['index_version']}`",
        f"- Reproduced exactly: **{'yes' if not problems else 'NO'}**"
        + ("" if not problems else " (see below)"),
        "",
        "| Criterion | Target | Dev pool | Held-out test-v2 | Status (test) |",
        "| --- | --- | --- | --- | --- |",
    ]
    if det is not None:
        lines.append(
            f"| SC1 deterministic index | byte-identical | {det['index_version']} | — | ✅ met |"
        )
    for key, label, target, op in CRITERIA:
        t = "—" if target is None else f"{op} {target:g}"
        lines.append(
            f"| {label} | {t} | {dev_card[key]:.3f} | {test_card[key]:.3f} | "
            f"{_met(float(test_card[key]), target, op)} |"
        )
    lines += [
        f"| SC4 REST contract (Schemathesis, every operation) | 0 violations | — | — | "
        f"{_gate(gates.get('contract'))} |",
        f"| Functional E2E (Playwright) | all pass | — | — | {_gate(gates.get('e2e'))} |",
        f"| Demo video from a cold start | MP4 | — | — | {_gate(gates.get('demo'))} |",
        "",
        "Recorded values: dev = `backend/evaluation/baseline.json`; test-v2 =",
        "`docs/evaluation/test-v2-results.json` (run once on 2026-11-12, configuration frozen).",
        "Interpretation, confidence intervals and limitations: `docs/evaluation-report.md`.",
    ]
    if problems:
        lines += ["", "## Differences", ""] + [f"- {p}" for p in problems]
    return "\n".join(lines) + "\n"


def write_zip(src: Path, target: Path) -> str:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(p for p in src.rglob("*") if p.is_file()):
            zf.write(path, Path(src.name) / path.relative_to(src))
    return hashlib.sha256(target.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dev", type=Path, required=True, help="dev summary.json")
    parser.add_argument("--test", type=Path, required=True, help="test summary.json")
    parser.add_argument("--determinism", type=Path, help="manifest from verify-determinism")
    parser.add_argument("--zip", help="also write <out>/../<NAME>.zip and SHA256SUMS")
    for gate in ("contract", "e2e", "demo"):
        parser.add_argument(f"--{gate}", choices=["passed", "failed", "skipped"], default="skipped")
    args = parser.parse_args(argv)

    dev, test = _load(args.dev), _load(args.test)
    det = _load(args.determinism) if args.determinism else None
    baseline = _load(BASELINE)
    problems = compare("dev", {**dev["scorecard"], "index_version": dev["index_version"]}, baseline)
    problems += compare(
        "test", {**test["scorecard"], "index_version": test["index_version"]}, _test_record()
    )
    if det is not None and det["index_version"] != test["index_version"]:
        problems.append(
            f"index: evaluated {test['index_version']}, determinism built {det['index_version']}"
        )

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "RESULTS.md").write_text(
        results_md(
            dev,
            test,
            det,
            problems,
            {"contract": args.contract, "e2e": args.e2e, "demo": args.demo},
        ),
        encoding="utf-8",
    )
    print((args.out / "RESULTS.md").read_text(encoding="utf-8"))

    if args.zip:
        target = args.out.parent / f"{args.zip}.zip"
        digest = write_zip(args.out, target)
        (args.out.parent / "SHA256SUMS").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
        print(f"bundle: {target} ({target.stat().st_size // 1024} KiB)\nsha256: {digest}")

    for p in problems:
        print(f"MISMATCH {p}", file=sys.stderr)
    failed_gates = [g for g in ("contract", "e2e", "demo") if getattr(args, g) == "failed"]
    for g in failed_gates:
        print(f"FAILED {g}", file=sys.stderr)
    return 1 if problems or failed_gates else 0


if __name__ == "__main__":
    sys.exit(main())
