# Manual test log

Plan: `test-plan.md` · Tester: <you> · Environment: Windows 11, Git Bash, local dev
(SQLite, `scripts/dev.sh`), index `6ce73ffaf982`.

## Phases 0–2 (2026-11-21 → 22)

All checks executed; fixes are in the commit "test(manual): phase 0-2 manual test fixes".
<!-- add per-ID rows here if you want them on record -->

## Phase 3: Validation, confidence and the /qa API (2026-11-23) ✅

| ID | Result | Evidence |
| --- | --- | --- |
| P3-01 | ✅ | healthz ok; readyz ready (index, database ok); version reports index 6ce73ffaf982 |
| P3-02/03 | ✅ | validated 0.838923 = 0.20·1.0 + 0.60·1.0 + 0.20·0.194613 (recomputed by hand) |
| P3-04 | ✅ | off-topic → `no_evidence`; amoxicillin dosing → `low_confidence` 0.41 (coverage 1.0) |
| P3-05 | ✅ ⚠️ | numeric gate correct (Unicode minus handled); found F-03 |
| P3-06 | ✅ | `/qa` ≡ `/api/v1/qa` (diff without request_id and latency_ms) |
| P3-07/08 | ✅ | 422 problem+json, no stack traces; found F-05 |
| P3-09/10 | ✅ | 405; X-Request-ID echoed in body and header |
| P3-11 | ✅ | 60 × 200, 20 × 429 in 0.9 s; `retry-after: 1`; security headers on errors |
| P3-12 | ✅ | qa_requests_total{status}, qa_confidence, qa_latency_seconds, qa_abstentions_total{reason} |
| P3-13 | ✅ | `IndexIntegrityError: chunks.jsonl sha256 != manifest` → "Application startup failed" |
| P3-14 | ✅ | /docs 200; contract 1.3.2; both routes in OpenAPI |
| P3-15 | ✅ | smoke passed; p50 21.0 ms, p95 28.4 ms (target ≤ 150 ms) |

Test-method notes: a Git Bash `curl` loop is too slow to exercise the token bucket (it
refills at 1 request/s while the loop runs), so P3-11 used a single Python process. The
`□` in console output is the Windows console rendering `…`.

## Findings register

| ID | Severity | Finding | Status |
| --- | --- | --- | --- |
| F-01 | Low (docs) | `signals.retrieval_score` described as a fused score; it is absolute cosine similarity | ✅ Fixed, contract 1.3.2 |
| F-02 | Medium (quality) | Answers can open with a "Purpose and Scope" sentence that echoes the question (hand hygiene; dev q-0028) | Open, Phase 4 re-test |
| F-03 | High (clinical completeness) | Vaccine storage answer validated at 0.85 but omitted 2–8 °C | Gate built (fixes this case), off by default; strict-xfail test |
| F-04 | Medium (validator) | Confidence takes the max over cited chunks, so extra citations can only raise it | Open, Phase 4 re-test |
| F-05 | Low (docs) | OpenAPI said malformed JSON is 400; it is 422 `json_invalid` (400 = undecodable body) | ✅ Fixed, contract 1.3.2 |
