# ADR-0006 — API contract strictness, additive `meta`, RFC 9457 errors

- **Status:** Proposed (implemented as contract v1 in Phase 0)
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

## Consequences

- **Positive:** clients and the generated TypeScript client have a single, stable shape;
  every contract change is visible in code review.
- **Negative:** the snapshot must be regenerated on purpose
  (`uv run python scripts/export_schemas.py`). That deliberate step is the point.

## Verification

`tests/unit/test_qa_contract.py`, `tests/api/test_qa_routes.py` and
`tests/contract/test_snapshots.py` (Phase 0); Schemathesis fuzzing (Phase 7).
