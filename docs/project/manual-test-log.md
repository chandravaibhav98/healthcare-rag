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

## Phase 6: React frontend (2026-11-23) ✅

| ID | Result | Evidence |
| --- | --- | --- |
| Audit | ✅ | `npm --prefix e2e run audit` on a fresh seed: 12/12 flows ok; Lighthouse accessibility 100 on all 9 routes, best practices 96; axe serious/critical 0, moderate/minor 0. One console 404 (missing favicon) → F-13 |
| Unit | ⚠️ | vitest 44/45: the first admin test timed out on the cold lazy import of the dashboard chunk (Windows) → F-14 |
| P6-01…06 | ✅ | disclaimer; validated answer with meter, signals and citation chips; evidence highlighting; abstention + escalate; friendly error with the API down; history and copy |
| P6-07…15 | ✅ | user → 403 on /admin; reviewer read-only (no Save/Activate/Run, no Audit Log); admin overview KPIs; review queue approve / correct / promote to gold; settings τ change previewed, saved, audited and restored to 0.6; evaluation run completes; keyboard-only navigation; dark mode and 375 px; Index shows 6ce73ffaf982 with no server path (F-11 confirmed in the UI) |

## Phase 7: Test hardening and quality gates (2026-11-23) ✅

| ID | Result | Evidence |
| --- | --- | --- |
| P7-00 | ✅ | preflight READY (0 warnings): docker 29.6, kubectl 1.36, kind 0.33, k6 2.4, ffmpeg 9.1, pwsh 7.7; trivy local; gitleaks via Docker image |
| P7-01 | ✅ | `scripts/test.sh --backend --frontend --coverage`: all gates passed; vitest 45/45, coverage statements 90.6% · branches 76.3% · lines 92.1% (gate ≥ 70%) |
| P7-02 | ✅ | Playwright 20/20 in 35 s (a11y on 8 routes, admin, assistant, auth/RBAC) against a disposable seeded stack |
| P7-05/06 | ✅ | "tests catch regressions", shown by real events during this test run rather than planted bugs: F-03 gate tripped the SC3 regression gates; contract snapshot caught the 1.3.2 bump; warnings-as-errors caught the deprecated `HTTP_422_UNPROCESSABLE_ENTITY`; F-11 path change broke the corrupted-index test |
| P7-01b | ⚠️ | full backend with coverage: 506 passed, 1 xfailed, TOTAL coverage **97%** (64 files at 100%); **45 errors at setup of every `[postgres]` variant** with Docker running → F-15 |
| P7-01c | ✅ | after the F-15 fix: `pytest -k postgres` 45 passed in 28.5 s (Testcontainers, postgres:17-alpine) |
| P7-03 | ✅ | k6 smoke 10 VUs × 30 s: p95 26.5 ms, 0/296 failed. Gate 50 VUs × 5 min: **p95 51.3 ms** (gate 300), p99 73 ms, **0 / 14 635 failed**, 48.6 req/s |
| P7-04 | ✅ | `security-scan.sh --strict`: pip-audit, npm audit, bandit, gitleaks (Docker), trivy fs (local 0.74.0; not a poisoned 0.69.4–0.69.6 build) all passed, no scanner skipped |

Note: during E2E uvicorn logged "Unsupported upgrade request / no WebSocket library" (a client tried a WebSocket upgrade through the preview proxy). Harmless: the app uses no WebSockets.

## Phase 8: Docker and Compose (2026-11-23) ✅ (F-19 open, awaiting upstream)

| ID | Result | Evidence |
| --- | --- | --- |
| P8-01 | ✅ | `docker-up.sh --demo`: first run failed (F-17); after the fix images built, stack healthy, seed ok (62 demo queries); smoke through nginx 7/7 PASS (`/qa` and `/api/v1/qa`, validated and abstain, 422 problem+json) |
| P8-02 | ✅ | postgres, api, web running (healthy); migrate and indexer exited (0) |
| P8-03 | ✅ | login through nginx with the generated compose password → 200; `/qa` validated 0.838923 (identical to local dev) |
| P8-04 | ✅ | non-root: api uid 10001, web uid 101 |
| P8-05 | ❌ | rag-api **443 MB** by CI's measure (`docker image inspect .Size`, gate < 400 MB; ADR-0014 expected ≈ 350 MB) → F-18. rag-web 98.5 MB, rag-index 8.5 MB |
| P8-06 | ✅ | `readyz` in Compose reports index 6ce73ffaf982 = the Windows build: **SC1 determinism holds across Windows and the Linux container build** |
| P8-07 | ✅ | CSP, X-Frame-Options DENY, nosniff, Referrer-Policy no-referrer through nginx; favicon present in the built web image (F-13 shipped) |
| P8-08 | ✅ | `docker compose restart api` → readyz ready, index 6ce73ffaf982 |
| P8-09 | ✅ | `docker-down.sh` (volumes kept) → `docker-up.sh --no-build` → reviewer (created only by the demo seed) logs in: 200, so the database volume persisted |
| P8-10 | ✅ | `--observability`: Prometheus target `rag-api` up; `sum(qa_requests_total)` = 13 after the smoke and 5 extra questions. Grafana dashboard: not opened before teardown |
| P8-11 | ❌ | `security-scan.sh --images --only trivy`: rag-api and rag-index clean; **rag-web: fixable CRITICAL** → F-19 |
| P8-12 | ✅ | `docker-down.sh --volumes`: no healthcare-rag volumes left |

## Phase 9: Kubernetes on kind (2026-11-23) ✅

| ID | Result | Evidence |
| --- | --- | --- |
| P9-01 | ⚠️ | `k8s-up.sh --recreate`: cluster (1 control plane + 2 workers, v1.37.0) and platform up, app images loaded; **postgres:18-alpine failed to load** (`ctr: content digest … not found`) → F-20; nothing applied |
| P9-01b | ⚠️ | after the F-20 fix: postgres loaded, migrate and seed jobs complete, api 2/2, web, gateway Programmed; smoke step gave up after 120 s ("gateway does not answer") although the gateway answered moments later → F-21 |
| P9-01c | ✅ | after the F-21 fix: `k8s-up.sh --no-build` ends with the smoke test through the gateway 7/7 PASS |
| P9-02 | ✅ | `k8s-status.sh`: HPA api 2–6 at 1%/70% CPU; PDB api and web minAvailable 1; 4 NetworkPolicies incl. default-deny-ingress; gateway `hcrag` Programmed; readyz ready through the gateway |
| P9-03 | ✅ | api: 2 replicas, init container `index`; pod `runAsNonRoot` uid/gid 10001, fsGroup 10001, seccomp RuntimeDefault; container `allowPrivilegeEscalation: false`, capabilities drop ALL, `readOnlyRootFilesystem: true`; probes startup /healthz, readiness /readyz, liveness /healthz |
| P9-04 | ✅ | through the gateway: index **6ce73ffaf982 (third platform: Windows, Compose, kind)**; `/qa` validated 0.838923; login with the generated secret 200 |
| P9-05 | ✅ | Pod Security Admission `restricted` refused an unhardened probe pod (namespace hardening enforced). A PSA-compliant busybox probe (uid 65534, seccomp, drop ALL) → `nc postgres 5432`: **blocked**; control: api → postgres allowed. NetworkPolicy is selective, not blanket |
| P9-06 | ✅ | `k8s-verify.sh` under 20 VUs of k6 load: rolling restart of every api and web pod → **zero failed requests**; index rollout to bfae4024806c (20/20 consecutive requests served it), `rollout undo` → 6ce73ffaf982 (20/20) → **zero failed requests** |
| P9-07 | ✅ | Playwright 20/20 in 32 s through the Envoy gateway against in-cluster PostgreSQL |
| P9-08 | ✅ | `--overlay prod` renders 22 objects: ExternalSecret, Gateway (TLS), HPA, 2 PDBs, 4 NetworkPolicies; no in-cluster postgres or StatefulSet (managed database in production) |

## Phase 10: CI/CD (2026-11-23, in progress)

| ID | Result | Evidence |
| --- | --- | --- |
| P10-03 | ❌ (known OI-39) | `git push origin main` **succeeded**: origin/main = local main = 7c4ac0a (five manual-test commits reached main without a PR or CI gate). `gh api …/rulesets` → 403 "Upgrade to GitHub Pro or make this repository public". Rulesets exist as code (`.github/rulesets/*.json`, `scripts/github-protect.sh`) but cannot be enforced on a private repository on GitHub Free; already recorded as OI-39 in the Phase 10 report. Owner decision pending: public repository, GitHub Pro, or documented acceptance |

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
| F-15 | Medium (test coverage on Windows) | All 45 `[postgres]` tests errored at setup when Docker was running: `Path(r"\\.\pipe\docker_engine").exists()` raised `OSError [WinError 231] All pipe instances are busy` | ✅ Fixed in `tests/persistence.py` (busy pipe = Docker available; host override on Windows): 45/45 `[postgres]` passed (commit 7c4ac0a) |
| F-16 | Low (test fidelity) | PostgreSQL tests ran on `postgres:17-alpine`; Compose and the local Kubernetes overlay deploy `postgres:18-alpine` | ✅ Fixed: tests use 18-alpine; 45/45 passed |
| F-17 | High (Windows deployability) | `scripts/docker-up.sh` failed on Git Bash: `MSYS_NO_PATHCONV=1` passed `/c/Users/...` to docker.exe → "unable to prepare context: path not found". Affects every docker-*/k8s-* script on Windows | Fix in `scripts/lib/common.sh` (`cygpath -m` for every script; first placed in containers.sh, which then broke the smoke step that docker-up calls with `MSYS_NO_PATHCONV` inherited): ✅ build, Compose stack and smoke through nginx all pass from Git Bash |
| F-18 | Low (CI gate fragility) | rag-api read 443 MB > the 400 MB CI budget by `docker image inspect .Size`; ADR-0014 recorded ≈ 350 MB | ✅ Measured: venv 211 MB (= ADR-0014); layers sum to **341 MB**, so the image did not grow. Docker Desktop's containerd store makes `inspect .Size` count compressed blobs too. CI gate now sums layer sizes (`scripts/ci/image-size.sh`): 341 MB < 400 |
| F-19 | High (supply chain) | trivy: a fixable CRITICAL vulnerability in `rag-web:local` (nginx/Alpine runtime image); the `images` CI job would block it | Packages: brotli-libs 1.2.0-r1 (CVE-2026-111497, fixed 1.2.1-r0), nginx 1.30.6-r1 (CVE-2026-113425 mail proxy, CVE-2026-121810 HTTP/3; fixed 1.30.7-r0), alpine 3.24.2; still present after `--no-cache --pull`, so the base tag itself lags. Neither nginx feature is enabled in our config. `apk upgrade --no-cache` added to the runtime stage → brotli-libs 1.2.1-r0 ✅. nginx is the nginx.org package and stays 1.30.6-r1 (fix not published there): scan still fails. **Owner decision (2026-11-23): A, wait for the upstream fix**; no suppression. Re-check with `scripts/docker-rebuild.sh --no-cache` + `security-scan.sh --images`; image publishing stays blocked by CI until it passes. Alternatives considered: Alpine-native nginx runtime (B), time-limited documented ignore (C) |
| F-20 | High (Windows deployability) | `k8s-up.sh` could not load the pulled multi-platform `postgres:18-alpine` into kind under Docker Desktop's containerd store: `kind load` and the `ctr --all-platforms` fallback both need content for every platform, but only amd64 is stored | ✅ Fixed in `load_images` (`docker save --platform` + `ctr import --platform` for the daemon's platform): deploy completed |
| F-21 | Medium (Windows deployability) | `k8s-up.sh` smoke always reported "gateway does not answer" although it answered: `wait_http` used `curl -o /dev/null`, and with `MSYS_NO_PATHCONV=1` curl.exe received the literal path, failed to write and returned an error on every probe. First diagnosed as timing (wait raised to 300 s, reverted) | ✅ Fixed: redirect in bash (`>/dev/null`); smoke through the gateway passes |
