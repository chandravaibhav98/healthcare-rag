> Part of the [documentation index](../README.md#documentation). Synthetic corpus only; not for clinical use.

# Tech stack

Pinned versions come from `backend/uv.lock`, `frontend/package-lock.json` and
`e2e/package-lock.json`; this page lists the main ones. Upgrades go through Dependabot
and the CI gates.

## Backend

| Area | Choice | Version |
| --- | --- | --- |
| Language | Python | 3.12 |
| Package manager | uv | lockfile `uv.lock` |
| Web framework | FastAPI + Uvicorn | 0.162.0 / 0.54.0 |
| Validation, settings | Pydantic, pydantic-settings | 2.14.3 / 2.16.2 |
| Vector search | faiss-cpu (`IndexFlatIP`) | 1.15.1 |
| Numerics | NumPy (float32) | 2.5.4 |
| Lexical search | In-house BM25 + Snowball stemmer | snowballstemmer 3.1.1 |
| Database access | SQLAlchemy 2 (async), Alembic | 2.1.8 / 1.20.1 |
| Drivers | asyncpg (PostgreSQL), aiosqlite (SQLite) | 0.32.0 / 0.22.1 |
| Auth | PyJWT (HS256), argon2-cffi (Argon2id) | 2.15.1 / 25.1.0 |
| Observability | structlog, prometheus-client, optional OTLP export | 26.1.0 / 0.26.0 |

## Frontend

| Area | Choice | Version |
| --- | --- | --- |
| UI | React, React Router | 19.3.1 / 8.5.1 |
| Build | Vite, TypeScript | 8.3.6 / 6.0.3 |
| Server state | TanStack Query | 5.107.1 |
| Runtime validation | Zod | 4.6.7 |
| Styling | Tailwind CSS | 4.3.5 |
| Charts | Recharts | 3.10.1 |
| API types | openapi-typescript (generated from `backend/openapi.json`) | 7.13.0 |
| Node | Node.js | 26 |

## Testing and quality

| Tool | Use |
| --- | --- |
| pytest, pytest-cov, Hypothesis | Unit, property-based and integration tests; coverage gates |
| Schemathesis | Contract fuzzing of every OpenAPI operation |
| Testcontainers | Real PostgreSQL in integration tests |
| Vitest, React Testing Library, MSW | Frontend unit and component tests |
| Playwright | E2E, accessibility (axe) gate, recorded demo |
| k6 | Load test (`/qa`, 50 VUs × 5 min) |
| ruff, mypy, ESLint, Prettier, tsc | Lint and type checks |
| pip-audit, npm audit, Bandit, Trivy, Gitleaks, detect-secrets | Security and supply chain |

## Runtime and delivery

| Area | Choice |
| --- | --- |
| Database | SQLite (dev and tests), PostgreSQL 18 (Compose, Kubernetes, production) |
| Containers | Docker multi-stage images: `rag-api`, `rag-web` (nginx-unprivileged), `rag-index` |
| Local orchestration | Docker Compose (+ Prometheus/Grafana profile) |
| Kubernetes | kind, Kustomize (base + `local` / `prod` overlays), Envoy Gateway (Gateway API) |
| CI/CD | GitHub Actions (`ci.yml`, `release.yml`, `demo.yml`), GHCR, SBOMs |

Decisions behind these choices are in the [ADRs](adr/README.md).
