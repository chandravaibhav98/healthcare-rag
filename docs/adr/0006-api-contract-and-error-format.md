# ADR-0006 — API contract strictness, additive `meta`, RFC 9457 errors

- **Status:** Proposed (contract v1.0 in Phase 0; **v1.1** in Phase 3, see Amendment 1)
- **Date:** 2026-11-07
- **Plan ref:** `plan.md` §3 ADR-006 · **Affects:** SC4, D1

## Context

The brief fixes `POST /qa` with input `{question, top_k}` and output
`{answer, citations, confidence, status}`. Later phases need more diagnostics (request
ID, index version, signals) without breaking that contract.

## Decision

1. The four brief fields are **top-level, exactly named, always present** and are never
   renamed or removed in v1. Additional data goes only in the optional `meta` object.
   Adding optional fields is a backward-compatible change.
2. **Canonical route** `POST /api/v1/qa`, plus the brief's **alias** `POST /qa`. Both
   are registered with the same handler, so their behaviour cannot diverge. Both appear
   in OpenAPI.
3. Request bounds: `question` 3–1000 characters after trimming; `top_k` 1–20 (default 5);
   unknown fields rejected (`extra = forbid`).
4. Invariants are enforced in the response model (`backend/app/api/schemas/qa.py`):
   citation ids are `1..n`; every `[n]` marker resolves to a citation; `validated`
   requires ≥ 1 citation and `numeric_ok`; `meta.abstained` ⇔ `needs_review`.
5. Every 4xx/5xx is **RFC 9457 `application/problem+json`** (`ProblemDetails`).
   Validation errors return `loc`, `msg` and `type` only. The rejected input is
   **never echoed**, because it may contain PHI (ADR-0009).
6. The contract is **snapshot-tested**: `backend/openapi.json` is committed, and CI and
   pre-commit fail if the code and the snapshot differ (`scripts/export_schemas.py --check`).

## Amendment 1 (Phase 3): contract 1.1.0, additive only

| Change | Why | Compatibility |
| --- | --- | --- |
| `Citation.superseded: bool = false` | ADR-0010: a superseded guideline may be shown as a candidate source but never as answer text; the UI badges it | Optional field, default false |
| `ProblemDetails.request_id` is now always filled | Correlates a client error with the server log line | Already in v1.0 as optional |
| 429 (rate limit) with `Retry-After` | Abuse protection per client (own token bucket, ADR note below) | New documented error |
| 503 (index not loaded) with `Retry-After: 5` | Fail closed while an index loads or after a failed load | New documented error |
| 500 as a generic problem without internals | The traceback goes to the log, never to the client | New documented error |
| The Phase 0 `501` is gone | The pipeline exists | Clients never relied on it |

The version is **1.1.0** (minor): nothing was removed or renamed and the four brief
fields are unchanged. `GET /healthz`, `GET /readyz` (503 with its own JSON body when not
ready) and `GET /version` are documented in OpenAPI; `GET /metrics` (Prometheus text) is
deliberately left out of the public contract.

**Rate limiting.** `slowapi`, named in the plan, was replaced by a 60-line token bucket
(`app/core/rate_limit.py`): typed, an injectable clock for deterministic tests, no
decorator that rewrites handler signatures, bounded memory. Limits are per process;
with several replicas the bucket store moves to Redis behind the same interface
(ADR-0008).

## Consequences

- **Positive:** clients and the generated TypeScript client have a single, stable shape;
  every contract change is visible in code review.
- **Negative:** the snapshot must be regenerated on purpose
  (`uv run python scripts/export_schemas.py`). That deliberate step is the point.

## Verification

`tests/unit/test_qa_contract.py`, `tests/api/test_qa_routes.py` and
`tests/contract/test_snapshots.py` (Phase 0); `tests/api/test_platform.py` (Phase 3:
probes, headers, CORS, metrics); Schemathesis fuzzing (Phase 7).
