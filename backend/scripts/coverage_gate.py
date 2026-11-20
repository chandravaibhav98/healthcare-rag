"""Coverage gates (plan Phase 7): fail when a package drops below its target.

    uv run pytest --cov --cov-report=json && uv run python scripts/coverage_gate.py

Targets use lines + branches (coverage.py's own "percent covered"):

    app/rag        >= 90%   the RAG domain: retrieval, generation, validation
    app/services   >= 85%   use cases
    overall        >= 80%   app + evaluation
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

TARGETS: Final = {"app/rag/": 90.0, "app/services/": 85.0, "": 80.0}


def percent(files: dict[str, dict[str, dict[str, int]]], prefix: str) -> float:
    covered = total = 0
    for name, data in files.items():
        if name.replace("\\", "/").startswith(prefix):
            s = data["summary"]
            covered += s["covered_lines"] + s.get("covered_branches", 0)
            total += s["num_statements"] + s.get("num_branches", 0)
    return 100.0 * covered / total if total else 100.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", nargs="?", default="coverage.json", type=Path)
    args = parser.parse_args(argv)
    files = json.loads(args.report.read_text(encoding="utf-8"))["files"]
    failed = False
    for prefix, target in TARGETS.items():
        value = percent(files, prefix)
        ok = value >= target
        failed |= not ok
        label = prefix.rstrip("/") or "overall"
        print(f"{'ok  ' if ok else 'FAIL'} {label:14s} {value:6.2f}%  (target {target:.0f}%)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
