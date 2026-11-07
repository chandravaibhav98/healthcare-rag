# ADR-0008 — Persistence, authentication and index distribution

- **Status:** Proposed (draft; finalised in Phases 5, 8 and 9)
- **Date:** 2026-11-07
- **Plan ref:** `plan.md` §3 ADR-008

## Decision (proposed)

| Concern | Choice | Alternative considered |
| --- | --- | --- |
| Database | PostgreSQL via SQLAlchemy 2.0 async + Alembic; SQLite only in unit tests | SQLite everywhere (weak for concurrency and k8s) |
| Auth | Local JWT (access + refresh), roles `user`, `reviewer`, `admin`, behind an `AuthProvider` protocol ready for OIDC | Keycloak/OIDC from day one (heavier) |
| `/qa` access | Authenticated by default; `ALLOW_ANONYMOUS_QA` for demos | — |
| Index distribution (k8s) | Immutable **OCI image** `rag-index:<index_version>`, copied by an init container into an `emptyDir` | PVC + build Job (mutable, harder to roll back) |
| Cache / queue | None until needed; Redis only when rate limiting must span replicas | Redis from the start |

## Consequences

- The API stays stateless, and rolling back the index is the same operation as rolling
  back an image tag.
- Phase 0 already exposes the related config keys (`DATABASE_URL`, `JWT_*`,
  `ALLOW_ANONYMOUS_QA`). Production refuses the dev JWT secret (`Settings` validator).

## Verification

RBAC matrix tests (Phase 5); index rollout/rollback drill (Phase 9).
