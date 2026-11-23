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

## Phase 4: Evaluation and threshold tuning (2026-11-23) ✅

| ID | Result | Evidence |
| --- | --- | --- |
| P4-01 | ✅ | run folders 20261123T080227Z (dev) / 080229Z (test): all 5 artefacts |
| P4-02 | ✅ | dev = baseline.json in every field; test = test-v2-reproduction.json in every field |
| P4-03 | ✅ | §1 = official Phase 12 results; §4.3 = current code (0.613 × 122/123 = 0.608); found F-06 |
| P4-04 | ✅ ⚠️ | 10 dev answers (seed 42): 5/5 validated correct, 4/5 padded (F-08); 2/5 abstentions missed a retrieved answer (F-09); q-0077 withheld a partial 5-step procedure (F-07) |
| P4-05 | ✅ | 5 test gold items: 5/5 labels correct (second-person spot-check toward ADR-0001's ≥ 20%) |
| P4-06 | ✅ | Threshold sweep (dev): τ 0.6 is the lowest with 0/22 false validations; 0.55 → 1/22 (4.5%, at the one-question granularity of n = 22) |
| P4-07 | ✅ | tests/regression green (Phase 3 close-out run) |
| P4-08 | ✅ ⚠️ | τ choice consistent with report §4.2. Risk: 14/123 dev and 5/83 test answerables sit in [0.60, 0.65); τ 0.65 → test pass 0.747 (SC3 fails). Test false validations survive any τ < 0.9 (q-1087 hepatitis A → hepatitis B schedule at 0.85): OI-27 reproduced, a signal problem, not a threshold problem |

**Phase 4 status:** SC1 ✅ · SC2 literal ❌ (ceiling-bound, ADR-0001; 74% of ceiling) · SC3 ✅ dev 0.919 / test 0.807 (thin margin) · safety ❌ on test (2/12, OI-27, reproduced).

F-02 measured: 1 / 130 answered dev questions (0.8%), downgraded to Low.

## Phase 5: Persistence, auth and admin APIs (2026-11-23) ✅

| ID | Result | Evidence |
| --- | --- | --- |
| P5-01 | ✅ | SQLite at revision 0002 = code head; `seed.sh --demo` created admin, reviewer, user; demo data 62 queries (45 validated, 17 needs_review, 2 redacted) |
| P5-02 | ✅ | `/auth/me` returns admin / reviewer / user for the three tokens |
| P5-03 | ✅ | RBAC matrix matches `tests/api/test_rbac_matrix.py`: R routes 401/403/200/200; `GET /audit-log` 401/403/403/200; `PUT /config` (empty body) 401/403/403/422, so the reviewer's 403 comes from the role check, not validation |
| P5-04 | ✅ | `/admin/queries?status=needs_review`: total 37, items carry status, reason, confidence, redactions, index_version |
| P5-05 | ✅ | `PUT /config` τ 0.6 → 0.95 (version 1): after the 30 s poll the hand-hygiene question (0.839) became `needs_review`; restored (version 2) → `validated` again |
| P5-06 | ✅ | stale `expected_version` → 409 (optimistic lock) |
| P5-07 | ✅ | audit log records both `config.update` entries with before/after values, comment, actor e-mail, request id and IP; logins audited too |
| P5-08 | ✅ | "Patient john.doe@mail.com phone 555-123-4567 MRN 12345678 …" stored as "Patient [EMAIL] phone [PHONE] [ID] …", redactions 3 |
| P5-09 | ✅ | 12 wrong passwords: 9 × 401 then 429 (10/min login limit, 2 logins already used) |
| P5-10 | ✅ | refresh via cookie 200; reuse of the rotated-out token 401; logout 204; refresh after logout 401 |
| P5-11 | ✅ ⚠️ | user abstains → escalation `queued`; note stored as "… Call me on [PHONE]"; reviewer correction with `promote_to_gold` appears in `gold.jsonl` (g2 = cdc-cc-002::summary-of-changes). Found F-10: `corrected_citations: ["not-a-chunk"]` accepted (201) |
| P5-11c | ✅ | 9 `auth.login_failed` entries, details `{"reason": "bad_credentials"}` (no password); `auth.refresh_reuse_detected` recorded |
| P5-12 | ✅ ⚠️ | active version 6ce73ffaf982 (72 docs, 346 chunks, corpus/config hashes); bogus activate → 404; found F-11 (server path in the response) |
| P5-13 | ✅ | production refuses the dev JWT secret, `LOG_QUESTION_TEXT=true` and CORS `*`, accepts a correct config; stateless mode: readyz ready (database `not_configured`), /qa validated, admin and auth 503 |

## Phase 6: React frontend (2026-11-23, in progress)

| ID | Result | Evidence |
| --- | --- | --- |
| Audit | ✅ | `npm --prefix e2e run audit` on a fresh seed: 12/12 flows ok; Lighthouse accessibility 100 on all 9 routes, best practices 96; axe serious/critical 0, moderate/minor 0. One console 404 (missing favicon) → F-13 |
| Unit | ⚠️ | vitest 44/45: the first admin test timed out on the cold lazy import of the dashboard chunk (Windows) → F-14 |
| P6-01…06 | ✅ | disclaimer; validated answer with meter, signals and citation chips; evidence highlighting; abstention + escalate; friendly error with the API down; history and copy |

## Next: quality re-test sprint (after Phase 12)

F-03, F-04, F-07, F-08, F-09 and OI-27 all change generation or validation. They are tuned
together on dev only and credited on a fresh test set (test-v3; test-v2 is spent).

## Findings register

| ID | Severity | Finding | Status |
| --- | --- | --- | --- |
| F-01 | Low (docs) | `signals.retrieval_score` described as a fused score; it is absolute cosine similarity | ✅ Fixed, contract 1.3.2 |
| F-02 | Low (quality) | Answers can open with a "Purpose and Scope" sentence that echoes the question (hand hygiene; dev q-0028) | Measured 1/130 dev (0.8%); no separate fix |
| F-03 | High (clinical completeness) | Vaccine storage answer validated at 0.85 but omitted 2–8 °C | Gate built (fixes this case), off by default; strict-xfail test |
| F-04 | Medium (validator) | Confidence takes the max over cited chunks, so extra citations can only raise it | Open, Phase 4 re-test |
| F-05 | Low (docs) | OpenAPI said malformed JSON is 400; it is 422 `json_invalid` (400 = undecodable body) | ✅ Fixed, contract 1.3.2 |
| F-06 | Low (docs) | Eval report §1 (official) vs §4.3 (current code) easy to misread | ✅ Fixed: footnote under §1 |
| F-07 | High (clinical safety) | Numbered procedures truncated by the 3-sentence cap (PPE donning: steps 2–4 of 5) | Open, Phase 4 re-test: lists all-or-nothing |
| F-08 | Medium (quality) | Answers padded with off-topic or repeated sentences (4/5 sampled validated) | Open, Phase 4 re-test (with F-04) |
| F-09 | Medium (recall) | Dense-cosine retrieval floor blocks lay paraphrases (2 answerable dev) but also blocks 10/22 unanswerables | Open, Phase 4 re-test: alternative floor signal, keep the 10 |
| OI-27 | High (clinical safety) | Test-split false validations survive any τ < 0.9: "hepatitis A schedule" answered with the hepatitis B schedule (0.85); measles incubation (0.67) | Known (report §6), reproduced in P4-05/P4-08; quality re-test sprint |
| F-10 | Medium (data integrity) | Review accepted malformed / non-existent `corrected_citations`; promoted corrections become gold labels | ✅ Fixed: schema `ChunkId` + active-index check (422), contract 1.3.3, regression test; live check 422/422/200 |
| F-11 | Low (security) | `GET /admin/index/versions` returns the server filesystem path (reviewer role can read it) | ✅ Fixed: response carries the folder name only (field kept, UI does not use it), contract 1.3.3, regression test |
| F-12 | Low (test tooling) | `e2e/audit/ui-audit.mjs` saved τ = 0.65 and left it, changing every later answer on the stack | ✅ Fixed: the audit restores 0.6 |
| F-13 | Low (UI) | No favicon: `/favicon.ico` 404 on every page (the audit's only console error, best practices 96) | ✅ Fixed: inline SVG favicon (CSP already allows `data:` images) |
| F-14 | Low (test reliability) | First admin vitest timed out on the cold lazy chunk; also `test_activating_a_corrupted_version…` read the server path that F-11 removed | ✅ Fixed: chunk warmed in `beforeAll`; test uses `IndexService.store_dir` |
