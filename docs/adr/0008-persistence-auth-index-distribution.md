# ADR-0008 — Persistence, authentication and index distribution

- **Status:** Accepted for persistence and auth (Phase 5). Index distribution in Kubernetes
  stays *Proposed* until Phase 9.
- **Date:** 2026-11-07 · revised 2026-11-13 (Phase 5)
- **Plan ref:** `plan.md` §3 ADR-008

## Decision

| Concern | Choice | Alternative considered |
| --- | --- | --- |
| Database | SQLAlchemy 2.x async + Alembic. **PostgreSQL** (asyncpg) for shared deployments; **SQLite** (aiosqlite) for local development and fast tests. Same models and migrations for both | PostgreSQL only (heavier local setup); SQLite only (weak for concurrency and k8s) |
| Persistence is optional | `DATABASE_URL` empty → the API runs stateless: `/qa` works, auth/admin answer 503, `/readyz` reports the database as `not_configured` | Make the database mandatory (the core RAG service would depend on it) |
| Migrations | Never at API start-up (replicas would race). `scripts/db-migrate.*` (a Job in k8s) runs first; the API **refuses to start** unless the schema is at Alembic head | Auto-migrate on boot |
| Passwords | argon2id (`argon2-cffi` defaults); rehash on login when parameters change; a dummy hash is verified for unknown e-mails so timing does not reveal accounts | bcrypt |
| Tokens | HS256 JWT. Access token 15 min, kept **in memory** by the SPA. Refresh token 7 days in an **httpOnly, SameSite=Strict cookie** scoped to `/api/v1/auth` (also returned in the body for non-browser clients) | Refresh token in localStorage (exposed to XSS) |
| Refresh rotation | Every refresh token works once. Tokens of one login form a *family*; presenting a used token revokes the whole family and is audited (`auth.refresh_reuse_detected`) | Long-lived, non-rotating refresh tokens |
| Authorisation | Roles `user` ⊂ `reviewer` ⊂ `admin` (`Role.allows`). `require_role(...)` dependency per route. The user row is read on **every** request, so deactivation and demotion apply at once | Trust the role claim until the token expires |
| `/qa` access | Anonymous allowed by default for the demo (`ALLOW_ANONYMOUS_QA=true`); a token that *is* sent must be valid (401, never a silent downgrade) | — |
| Login throttling | Token bucket per client address (`LOGIN_RATE_LIMIT`, default 10/min), in-process | Redis-backed limiter (OI-11) |
| Runtime tuning | `app_config` rows are versioned; `PUT /admin/config` uses optimistic locking (`expected_version`, 409 on conflict) and is audited; other pods poll every `CONFIG_POLL_SECONDS` | Environment-only, immutable threshold |
| Index versions | Boot index plus `INDEX_STORE_DIR/<version>/` are registered in `index_versions`. Activation verifies hashes, hot-swaps the registry, is audited, and other pods follow via the poller. **Rebuild from the API is development-only** and never activates by itself | Rebuild in production from the UI |
| Index distribution (k8s) | Immutable **OCI image** `rag-index:<index_version>`, copied by an init container into an `emptyDir` (Phase 9) | PVC + build Job (mutable, harder to roll back) |
| Cache / queue | None. Query-log writes use an in-process bounded queue; Redis only when limits must span replicas | Redis from the start |

### RBAC matrix (enforced by `tests/api/test_rbac_matrix.py`)

| Route (`/api/v1/admin/...`) | user | reviewer | admin |
| --- | --- | --- | --- |
| `GET stats`, `queries`, `queries/{id}`, `reviews`, `reviews/export/gold.jsonl`, `eval-runs`, `eval-runs/{id}`, `index/versions`, `documents`, `config` | 403 | ✅ | ✅ |
| `POST reviews/{query_id}` | 403 | ✅ | ✅ |
| `POST eval-runs`, `POST index/versions/{v}/activate`, `GET/POST index/rebuild`, `PUT config`, `GET audit-log` | 403 | 403 | ✅ |

Anonymous callers get 401 with `WWW-Authenticate: Bearer` on every admin route. A route
added without a matrix entry fails the test.

## Consequences

- The RAG service keeps working when the database is down or absent; only the dashboard
  features degrade. `/readyz` fails when a *configured* database is unreachable, so a
  pod with a broken connection is drained.
- One schema serves both engines. SQLite keeps the inner loop fast (template database
  copied per test); every persistence test also runs on PostgreSQL (Testcontainers in
  CI, or `TEST_DATABASE_URL`).
- Rotation plus reuse detection limits the damage of a stolen refresh token to one use.
- Not built yet: the `AuthProvider` protocol for OIDC. Local accounts are the only
  provider (OI-24).

## Verification

Phase 5: `tests/api/test_auth.py` (rotation, reuse, cookie flags, deactivation,
demotion, rate limit), `tests/api/test_rbac_matrix.py` (17 routes × 4 callers),
`tests/integration/test_migrations.py` (no model/DDL drift, round trip, start-up refusal)
on SQLite and PostgreSQL. Phase 9: index rollout/rollback drill.
