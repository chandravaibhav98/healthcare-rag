# Phase 5 Report — Persistence, Auth & Admin APIs

- **Date:** 2026-11-13 · **Plan ref:** `plan.md` §4 Phase 5 · Milestone M2 (backend part)
- **Result:** every Phase 5 deliverable is built. All 17 admin routes, the 4 auth routes
  and the persistence layer are tested on **SQLite and PostgreSQL**; the RBAC matrix
  (17 routes × 4 callers = 68 cases) is green. **Exit criteria met.**
- **API contract:** 1.2.0 (additive: auth and admin routes, optional bearer on `/qa`).
  `/qa` and its four spec fields are unchanged.

## 1. Deliverables

| Plan item | Status | Where |
| --- | --- | --- |
| Data model: `users`, `query_log`, `reviews`, `eval_runs`, `index_versions`, `audit_log`, `app_config` (+ `refresh_tokens`) | ✅ one Alembic migration, no drift on either engine | `app/db/`, `migrations/` |
| Repositories (pagination with whitelisted sort and a unique tie-breaker) | ✅ | `app/repositories/` |
| `scripts/db-migrate.*` | ✅ upgrade, `--revision`, `--downgrade` (refused in production), `--current` | `scripts/`, `backend/scripts/db.py` |
| `scripts/seed.*` (admin + demo data) | ✅ idempotent; `--demo` answers 62 real questions through the pipeline over 7 days, with reviews; `--reset` refused in production | `backend/scripts/seed.py` |
| Auth: login, refresh, me (+ logout); argon2id; JWT; `require_role` | ✅ refresh rotation with reuse detection; httpOnly cookie | `app/api/routes/auth.py`, `app/services/auth_service.py` |
| `GET /admin/stats?from&to` | ✅ volume, pass and abstention rate, mean confidence, p50/p95 latency, reasons, top topics, daily series | `routes/admin/stats.py` |
| `GET /admin/queries`, `/queries/{id}` | ✅ 9 filters, 3 sort keys; detail shows signals, evidence, withheld answer, review | `routes/admin/queries.py` |
| `GET /admin/reviews?status=pending`, `POST /admin/reviews/{query_id}` | ✅ pending / reviewed / all, verdict and promoted filters; upsert (201 then 200) | same |
| Gold feedback loop (export as JSONL) | ✅ `GET /admin/reviews/export/gold.jsonl` (candidates; DATASET_CARD §7) | `app/services/admin_service.py` |
| `GET/POST /admin/eval-runs`, `GET /admin/eval-runs/{id}` | ✅ async, one at a time (409), stale runs expire; same code as the CLI gate | `app/services/eval_service.py` |
| `GET /admin/index/versions`, `POST …/{v}/activate`, `POST /admin/index/rebuild` (dev only) | ✅ verified hot swap, audited; rebuild refused in production even if enabled | `app/services/index_service.py` |
| `GET /admin/documents` | ✅ corpus inventory with chunk and token counts, filters | `routes/admin/index.py` |
| `GET/PUT /admin/config` | ✅ versioned, optimistic lock, audited, polled by other pods | `app/services/config_service.py` |
| `GET /admin/audit-log` | ✅ action-prefix, actor and time filters | `routes/admin/audit.py` |
| PHI-redaction hook | ✅ before persistence; clinical quantities untouched | `app/core/redaction.py` (ADR-0009) |
| Retention purge job | ✅ in-process loop + CLI (`scripts/maintenance.py purge`) | `app/services/maintenance.py` |
| Integration tests on PostgreSQL via Testcontainers | ✅ every persistence test is parametrised `[sqlite]` / `[postgres]`; Testcontainers in CI, `TEST_DATABASE_URL` locally | `tests/persistence.py` |
| RBAC matrix (each role × endpoint) | ✅ fails if a route has no matrix entry | `tests/api/test_rbac_matrix.py` |

## 2. Design decisions taken in this phase

| Decision | Why |
| --- | --- |
| **Persistence is optional.** No `DATABASE_URL` → stateless `/qa`; auth/admin 503 | The core RAG service must not depend on the dashboard database |
| **SQLite is the local default**, PostgreSQL for shared deployments | Fresh clone works without Docker; one schema for both |
| **No migrations at start-up**; the API refuses a schema that is not at head | Replicas would race; fail fast like the index manifest check |
| **Query log written off the request path** (bounded queue, batched inserts, drops counted in `qa_log_dropped_total`) | A slow database must never slow or fail an answer |
| **Questions stored redacted, always**; raw text never stored | Reviewers need the question; the database must not hold identifiers (ADR-0009) |
| **Runtime tuning snapshot per request** (`TuningHolder`) | A request never mixes old and new threshold or weights |
| **API evaluations use the dev pool only** and the live tuning | The held-out test set cannot be tuned against from a dashboard (ADR-0001) |
| **Each admin router carries its full prefix** | FastAPI 0.16x no longer flattens nested routers; metrics need full route templates |

## 3. Verification

| Check | Result |
| --- | --- |
| Backend tests, SQLite + PostgreSQL (local PostgreSQL 16.2 via `TEST_DATABASE_URL`) | **456 passed, 0 skipped** (Phase 4: 268) |
| Backend tests without PostgreSQL | 419 passed, 37 PostgreSQL variants skipped with a reason |
| Coverage (`app/`) | 96% lines+branches (greenlet-aware coverage enabled) |
| ruff · ruff format · mypy --strict | clean |
| Evaluation gate | unchanged scorecard; the API evaluation run reproduces `baseline.json` exactly (`tests/integration/test_eval_api.py`) |
| End-to-end on uvicorn | migrate → seed `--demo` → login → stats, queue, explorer, refresh via cookie, evaluation run, gold export, `/metrics` labels |
| Scripts (bash and PowerShell) | `db-migrate`, `seed`, `dev` (migrates when `DATABASE_URL` is set) |

**Not verified here:** the Testcontainers start-up itself (`postgres:17-alpine`), because
this build machine has no Docker daemon. The same tests ran against a real PostgreSQL 16.2
through `TEST_DATABASE_URL`; the Testcontainers path first runs in the Linux CI job.

Bugs found by the new tests and fixed before hand-off: percentile rank off by one
(nearest-rank used rounding), the 18-byte dev JWT secret (below HS256's 32-byte minimum;
now 40 bytes), metrics/log `route` labels losing the router prefix, and a leaked database
connection when start-up fails.

## 4. Open issues

Closed: **OI-12** (query log and candidate answers now in the database for reviewers).
New (plan §10): OI-23 (gold candidates need a small import tool), OI-24 (OIDC
`AuthProvider` not built), OI-25 (statistics computed in Python; fine to ~1M rows per
window), OI-26 (PostgreSQL variants do not run on the Windows CI runner). OI-11 now also
covers the login limiter.

## 5. Hand-off to Phase 6

The React dashboard can be built against `backend/openapi.json` (contract 1.2.0): every
screen in plan Phase 6 has its endpoint, and `scripts/seed.sh --demo` gives realistic
data. After merging: update `DATABASE_URL` in your `.env` (see the note in the README),
then run `scripts/db-migrate.sh` and `scripts/seed.sh --demo`.
