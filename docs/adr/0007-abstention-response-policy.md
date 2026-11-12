# ADR-0007 — Abstention response policy (patient-safety posture)

- **Status:** Proposed (implemented in Phase 3; reviewer storage in Phase 5)
- **Date:** 2026-11-07
- **Plan ref:** `plan.md` §3 ADR-007 · **Affects:** SC3, D3

## Context

Showing weakly supported clinical text as an answer is the main safety failure this
system must avoid (risk R8). The system must still stay useful and citation-first when
it abstains.

## Decision (proposed)

When `status = needs_review`:

- `answer` is a fixed abstention message: *"The indexed guidelines do not contain
  sufficient evidence to answer this confidently. Please consult the cited sources or
  escalate for review."*
- `citations` still lists the best candidate sources, so the user can read the evidence.
- `meta.abstained = true` and `meta.reason` explains why (`no_evidence`,
  `below_retrieval_floor`, `numeric_mismatch`, `low_confidence`).
- The low-confidence **candidate answer** is stored for the `reviewer` and `admin` roles
  only (review queue, Phase 5). It is never returned to a `user`.

## Implementation (Phase 3)

`app/services/qa_service.py`:

- The candidate sources are the citations of the withheld answer when one was generated,
  otherwise the top retrieval hits; at most **3** (`CANDIDATE_SOURCES`), renumbered `1..n`.
- `confidence` reports the real computed score for `numeric_mismatch` and
  `low_confidence`, and `0.0` when nothing was generated (`no_evidence`,
  `below_retrieval_floor`). Reporting the real score lets reviewers see how close it was.
- The withheld candidate answer travels only inside the internal `QAOutcome` handed to
  observers. Until the review queue exists (Phase 5) it is written to the structured
  query log, and only when `LOG_QUESTION_TEXT=true` (never in production, ADR-0009).
  A test asserts the candidate text never appears in the HTTP response.

## Consequences

- **Positive:** weakly supported text never reaches end users, and every abstention can
  be explained and reviewed.
- **Negative:** some correct answers are withheld (false abstentions). This is measured
  as the Phase 4 pass rate and tuned on dev only.

## Verification

Contract invariants (Phase 0); `tests/unit/test_qa_service.py` and
`tests/api/test_qa_routes.py` (Phase 3); E2E abstention flow (Phase 7).
