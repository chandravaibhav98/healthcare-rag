# ADR-0014 — Container images and the Compose stack

- **Status:** Accepted (Phase 8)
- **Date:** 2026-11-20
- **Plan ref:** `plan.md` §4 Phase 8 · **Builds on:** ADR-0008 (index as an OCI image), ADR-0012 (same origin)

## Context

Phase 8 packages the service for any machine with Docker. Three things shape the images:
the index must stay byte-identical to the CI build (SC1), the API must not be reachable
except through the web tier, and the images must be safe to run on a cluster with the
"restricted" Pod Security Standard (Phase 9) without changes.

## Decision

| Concern | Choice | Why / alternative |
| --- | --- | --- |
| Images | Three: `rag-api`, `rag-web`, `rag-index:<index_version>` | The index rolls out and back independently of the code (ADR-0008). One image per concern keeps each small |
| API base | `python:3.12-slim`, multi-stage, `uv sync --frozen --no-dev` into `/app/.venv`; source run from `/app/backend` (not installed) with `PYTHONPATH` | `REPO_ROOT` is derived from the source path; installing the package would move it into site-packages. Distroless noted as later hardening (no shell for debugging) |
| Runtime hardening | UID 10001 (api), 101 (web), 65534 (index); read-only root filesystem; `/tmp` as tmpfs; all capabilities dropped; `no-new-privileges`; bytecode compiled at build time | The same images pass Kubernetes' restricted profile unchanged |
| Index image | Built by the same pipeline as CI (`pipeline.py build` + `verify`, `PYTHONHASHSEED=random`), final stage `busybox` with the files and `cp`. Its `index_version` is checked against the determinism job in CI | Tiny, and its only job is to be copied into the API's volume. Chunking build-args allow a second valid index for rollout tests |
| Web | Node build stage → `nginx-unprivileged`; nginx serves the SPA, proxies `/api`, `/qa` and the probes to `api:8000`; `/metrics` and `/docs` are not exposed | Same origin: no CORS, and the SameSite=Strict refresh cookie works (ADR-0012) |
| Security headers | CSP `default-src 'self'; script-src 'self'; style-src 'self'` (no `unsafe-inline`; verified with the E2E suite and a console-error sweep), `nosniff`, `no-referrer`, `DENY` framing, COOP/CORP, a Permissions-Policy | The SPA needs nothing inline; a strict policy costs nothing |
| Client address | Uvicorn `--proxy-headers`, `FORWARDED_ALLOW_IPS=*` only where the API is unreachable except through the proxy (Compose internal network, Kubernetes NetworkPolicy) | Rate limiting and the audit log need the real client, not nginx's address |
| Logs | Uvicorn access log off; the app's JSON line per request (with `request_id`) is the access log; nginx forwards/creates `X-Request-ID` | One structured log line per request, correlated across tiers |
| Compose | `postgres → migrate → indexer → api → web` via `depends_on` conditions; `backend` network is `internal: true`; only `web` publishes a port, on 127.0.0.1; secrets generated into a git-ignored `.env` | The API and database are unreachable from outside; nothing secret is committed |
| Observability | Optional `docker-compose.observability.yml`: Prometheus scrapes `api:8000/metrics` on the internal network; Grafana with a provisioned RAG dashboard (pass share, latency quantiles, abstentions by reason, active index_version, query-log drops) | Opt-in so the default stack stays small |

## Consequences

- `scripts/docker-up.*` gives a production-shaped stack in one command; `--demo` switches
  to `APP_ENV=staging` because the demo accounts share a password, which production refuses.
- Image size: the API adds ~223 MB (virtualenv: numpy and faiss dominate) to the base
  image, about 350 MB in total with `python:3.12-slim`; CI enforces < 400 MB.
- Base images are referenced by tag. Digest pinning with automated updates belongs to the
  release pipeline (Phase 10, OI-35).
