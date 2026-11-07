# ADR-0009 — Healthcare data handling (PHI minimisation)

- **Status:** Proposed (partly implemented in Phase 0; completed in Phases 3 and 5)
- **Date:** 2026-11-07
- **Plan ref:** `plan.md` §3 ADR-009 · **Risk:** R9

## Context

The corpus is synthetic, but users can type real patient details into a question.
Questions therefore have to be treated as potentially containing PHI.

## Decision (proposed)

1. `LOG_QUESTION_TEXT` controls whether raw question text is logged or persisted.
   **Production refuses `true`** (enforced by the `Settings` validator since Phase 0).
2. Validation errors never echo the rejected input (Phase 0, `app/api/errors.py`;
   tested in `tests/api/test_qa_routes.py`).
3. A PHI-redaction hook (regex rules for MRN, phone, email and date-of-birth patterns)
   runs before anything is persisted (Phase 5).
4. `query_log` has a retention TTL (`QUERY_LOG_RETENTION_DAYS`, default 30) enforced
   by a purge job (Phase 5).
5. Logs never contain secrets. `SecretStr` is used for keys, and `detect-secrets` runs in
   pre-commit and CI.

## Consequences

- **Positive:** reduces the impact of accidental PHI entry; production misconfiguration
  is rejected at start-up rather than discovered in an audit.
- **Negative:** less raw data for debugging in production. Mitigation: redacted logs
  plus request IDs.

## Verification

Phase 0 config and API tests; Phase 5 redaction unit tests with a PHI fixture set.
