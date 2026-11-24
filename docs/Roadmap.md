> Part of the [documentation index](../README.md#documentation). Synthetic corpus only; not for clinical use.

# Roadmap

Work that is known but not done. Live status of test findings is in the
[test plan Open Items](../test-plan.md#open-items); design-level open issues are in
[`plan.md`](../plan.md) §10.

## 1. Decisions needed from the owner or client

| Item | Options |
| --- | --- |
| SC2 reading (P@5 0.417 vs 0.65) | Accept the ceiling argument, change the relevance definition, or invest in retrieval ([technical summary §5](technical-summary.md)) |
| ADR-0001 / ADR-0002 sign-off | Relevance definition; composite confidence |
| Licence | The client chooses; none is granted today |
| Branch protection | Public repository or paid GitHub plan, or accept unprotected `main` |
| nginx CVEs in `rag-web` (F-19) | Waiting for the upstream fix (chosen), suppress with an expiry, or change base image |

## 2. Quality

- Reduce false validations on unanswerable questions (2 / 12 on test; target ≤ 5 %).
- Value questions (temperatures, durations, frequencies): the value-type gate exists but
  is off because it lowered the pass rate (F-03, F-04); re-test with a better candidate pool.
- Remaining findings F-07, F-08, F-09 and OI-27 from the manual test log.

## 3. Product backlog (optional)

| Idea | Value |
| --- | --- |
| Conflict detection when cited sources disagree | Clinical safety |
| Version-aware retrieval (prefer latest `effective_date`, "superseded" badge) | Guideline governance |
| Cross-encoder reranker behind a feature flag | Precision |
| Optional LLM generator behind the same validator, with an A/B evaluation | Fluency without losing grounding |
| Semantic cache keyed by `index_version` | Latency |
| OpenTelemetry traces (retrieval, generation, validation spans) | Observability |
| Per-topic confidence calibration curves | Statistical rigour |

## 4. Production readiness

- Connect a real `DocumentSource` with document-level access control ([RUNBOOK §4](../RUNBOOK.md)).
- External secrets, managed PostgreSQL, TLS certificates for the prod overlay.
- Redis-backed rate limiting if more than one API replica must share limits.
- Scale path from `IndexFlatIP` to IVF/HNSW or an external vector store ([RUNBOOK §7](../RUNBOOK.md)).
