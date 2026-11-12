"""Smoke test a running API: probes, both `/qa` paths, schema validity, optional latency.

    uv run python scripts/smoke.py [--base-url http://127.0.0.1:8000] [--bench 200]

Uses only the standard library for HTTP, so it can run against any deployment (local,
Docker, Kubernetes). Every `/qa` body is validated against the Pydantic contract.
Exit code 0 = all checks passed.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.schemas.qa import QAResponse

ANSWERABLE = "How long should hand hygiene with alcohol-based handrub take?"
UNANSWERABLE = "Who won the football world cup?"


def call(base: str, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(  # noqa: S310  (URL comes from the operator's CLI flag)
        base.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-Request-ID": "smoke-test"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"null")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--bench", type=int, default=0, help="extra /qa calls for p50/p95")
    parser.add_argument("--p95-budget-ms", type=float, default=150.0)
    args = parser.parse_args()
    failures: list[str] = []

    def check(label: str, ok: bool, info: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}{f'  ({info})' if info else ''}")
        if not ok:
            failures.append(label)

    try:
        code, _ = call(args.base_url, "GET", "/healthz")
    except OSError as err:
        print(f"Cannot reach {args.base_url}: {err}. Is the API running (scripts/dev.sh)?")
        return 1
    check("GET /healthz", code == 200)
    code, ready = call(args.base_url, "GET", "/readyz")
    check("GET /readyz", code == 200, f"index {ready.get('index_version') if ready else None}")

    for path in ("/api/v1/qa", "/qa"):
        for question, expected in ((ANSWERABLE, "validated"), (UNANSWERABLE, "needs_review")):
            code, body = call(args.base_url, "POST", path, {"question": question, "top_k": 5})
            try:
                resp = QAResponse.model_validate(body)
                ok = code == 200 and resp.status == expected
                info = f"{resp.status}, confidence {resp.confidence}"
            except ValueError as err:
                ok, info = False, f"schema violation: {err}"
            check(f"POST {path} → {expected}", ok, info)

    code, problem = call(args.base_url, "POST", "/qa", {"question": "x"})
    check("POST /qa invalid → 422 problem+json", code == 422 and problem.get("status") == 422)

    if args.bench > 0:
        timings: list[float] = []
        statuses: dict[int, int] = {}
        for i in range(args.bench):
            question = ANSWERABLE if i % 2 == 0 else UNANSWERABLE
            started = time.perf_counter()
            code, _ = call(args.base_url, "POST", "/api/v1/qa", {"question": question})
            timings.append((time.perf_counter() - started) * 1000)
            statuses[code] = statuses.get(code, 0) + 1
        # A 429 returns in well under a millisecond and would fake a good p95.
        check(
            "benchmark requests all answered (200)",
            set(statuses) == {200},
            f"status counts {statuses}; raise RATE_LIMIT_QA for benchmarking",
        )
        timings.sort()
        p50 = statistics.median(timings)
        p95 = timings[max(0, round(0.95 * len(timings)) - 1)]
        check(
            f"p95 latency ≤ {args.p95_budget_ms:g} ms",
            p95 <= args.p95_budget_ms,
            f"n={len(timings)}, p50 {p50:.1f} ms, p95 {p95:.1f} ms (end-to-end over HTTP)",
        )

    print("\nSmoke test " + ("FAILED: " + ", ".join(failures) if failures else "passed."))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
