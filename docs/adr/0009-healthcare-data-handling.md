# ADR-0009 — Healthcare data handling (PHI minimisation)

- **Status:** Accepted (implemented in Phases 0, 3 and 5)
- **Date:** 2026-11-07 · revised 2026-11-13 (Phase 5)
- **Plan ref:** `plan.md` §3 ADR-009 · **Risk:** R9

## Context

The corpus is synthetic, but users can type real patient details into a question.
Questions therefore have to be treated as potentially containing PHI. Phase 5 adds a
database, so questions are now stored, not only logged.

## Decision

1. **Logs:** `LOG_QUESTION_TEXT` controls whether raw question text appears in log
   events. **Production refuses `true`** (`Settings` validator since Phase 0).
2. **Database:** the review queue needs the question, so `query_log` always stores it,
   but only **after redaction** (`app/core/redaction.py`, applied in
   `QueryLogWriter` before a row leaves the process). The raw text is never written.
   Each row records how many replacements were made (`redactions`).
3. **Redaction rules** (conservative, prefer over-redaction): e-mail → `[EMAIL]`; MRN /
   medical record / patient id / hospital / NHS numbers and SSN shapes → `[ID]`; dates
   of birth and calendar dates → `[DATE]`; phone numbers → `[PHONE]`; names after a title
   (Mr, Mrs, Dr…) or "patient named" → `[NAME]`; long digit runs → `[ID]`. Clinical
   quantities ("2–8 °C", "70%", "15 minutes", "1,000 ppm", "2 doses") are left alone.
4. **Retention:** `query_log` rows older than `QUERY_LOG_RETENTION_DAYS` (default 30) and
   expired refresh tokens are deleted by a purge that runs every
   `RETENTION_PURGE_INTERVAL_MINUTES` in the API and on demand
   (`scripts/maintenance.py purge`, a CronJob in Phase 9). Each purge that deletes
   anything is audited (`retention.purge`).
5. **Access:** stored questions and withheld candidate answers are visible to the
   `reviewer` and `admin` roles only (ADR-0008 RBAC matrix).
6. **Errors and caches:** validation errors never echo input; responses carry
   `Cache-Control: no-store`; the gold export carries only redacted text.
7. **Secrets:** `SecretStr` for keys and URLs; `detect-secrets` in pre-commit and CI.

## Residual risk

Rules cannot recognise a bare name without a title ("can Maria Lopez get the vaccine?").
That is why production never logs raw text, `query_log` has a retention period, and the
table is reviewer-only. A model-based de-identification step would be the next layer if
real users are onboarded (RUNBOOK, Phase 12).

## Consequences

- **Positive:** reviewers get what they need without the database holding identifiers;
  a misconfigured production deployment is rejected at start-up.
- **Negative:** over-redaction can hide a clinically relevant date in rare questions.
  Mitigation: the `redactions` count lets reviewers see that text was replaced.

## Verification

`tests/unit/test_redaction.py` (PHI fixture set and clinical non-changes),
`tests/api/test_admin.py::test_qa_outcomes_are_persisted_redacted_and_attributed`
(raw PHI never reaches the database), `test_retention_purge`, and the Phase 0/3 config,
error-echo and header tests.
