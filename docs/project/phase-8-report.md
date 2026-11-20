# Phase 8 Report — Containerization (Docker & Compose)

- **Date:** 2026-11-20 · **Plan ref:** `plan.md` §4 Phase 8 · Milestone M3 (part 1)
- **Result:** every deliverable is built. `scripts/docker-up.sh` (and `.ps1`) builds the
  three images, starts PostgreSQL → migrations → index → API → web, seeds accounts and
  smoke-tests through nginx. Against that stack the **20 E2E tests pass** and a **50-VU
  k6 run** has 0 failed requests. The index image reproduces **index_version
  6ce73ffaf982**, the determinism build. **Exit criterion met** (with OI-37 below).
- **Decisions:** ADR-0014.

## 1. Deliverables

| Deliverable | Where | Notes |
| --- | --- | --- |
| `api.Dockerfile` | `deploy/docker/` | Multi-stage `uv sync --frozen --no-dev`; UID 10001; read-only root; bytecode precompiled; `HEALTHCHECK` via stdlib; `--proxy-headers`; JSON access log only |
| `web.Dockerfile` | `deploy/docker/`, `nginx/` | Node 26 build → `nginx-unprivileged`; SPA fallback, gzip, immutable `/assets` caching, `no-cache` HTML; CSP without `unsafe-inline` plus `nosniff`, `no-referrer`, `DENY`, COOP/CORP, Permissions-Policy; `/metrics` and `/docs` not exposed |
| `index.Dockerfile` | `deploy/docker/` | Same pipeline as CI with `PYTHONHASHSEED=random`; prints `index_version`; busybox final stage that copies into `/target` |
| `.dockerignore` | repo root | Context excludes VCS, venvs, node_modules, tests, docs, secrets |
| `docker-compose.yml` | `deploy/compose/` | `postgres` (healthcheck, volume), `migrate`, `indexer`, `seed` (on demand), `api`, `web`; internal `backend` network; only `web` published, on 127.0.0.1; all app containers read-only, no capabilities, `no-new-privileges` |
| Observability profile | `deploy/compose/docker-compose.observability.yml`, `observability/` | Prometheus v3.16.0 + Grafana 13.3.1 with a provisioned 11-panel RAG dashboard |
| Scripts | `scripts/docker-{up,down,rebuild,logs}.{sh,ps1}`, `lib/containers.sh`, `lib/Containers.psm1` | Generated secrets in `deploy/compose/.env`; content-checked rebuilds; `--demo`, `--observability`, `--port` |
| Image scan | `scripts/security-scan.* --images` | trivy image on all three: no fixable CRITICAL |
| CI | `.github/workflows/ci.yml` job `images` | docker-up, index_version = determinism job, API size < 400 MB, E2E against Compose, image scan |

## 2. Verification

| Check | Result |
| --- | --- |
| `docker-up.sh --demo` and `docker-up.ps1 --demo` from no `.env` | Both: built, healthy in ~18 s, seeded, 7/7 smoke checks through nginx |
| E2E (`E2E_BASE_URL=http://localhost:8080`) | **20/20** (functional journeys + axe on every route), with the strict CSP |
| Browser console sweep, all 9 routes | 0 errors, 0 CSP violations |
| k6, 50 VUs × 60 s through nginx (API + PostgreSQL + k6 on 2 vCPU) | 2,742 requests, 0 failed, p95 237 ms |
| `index_version` from the image | 6ce73ffaf982 = `backend/evaluation/baseline.json` |
| Hardening | `api` runs as 10001, `web` as 101; writing to `/` fails (read-only) |
| `docker-down.sh --volumes`, `docker-rebuild.sh`, `docker-logs.*` | Work; a stale database volume with a new `.env` is detected and explained |
| Image size | API adds ~223 MB to its base (virtualenv 211 MB); ≈ 350 MB with `python:3.12-slim` (CI enforces < 400 MB) |

## 3. Defects found

| # | Defect | Fix |
| --- | --- | --- |
| 1 | `.dockerignore` pattern `**/coverage*` silently excluded `app/rag/validation/coverage.py` | Narrowed to the coverage report files; the index build failed loudly, so it was caught at once |
| 2 | Scripts run as `python scripts/x.py` could not import `app` (it is not installed in the image) | `PYTHONPATH=/app/backend` in both images |
| 3 | A fresh Docker volume is root-owned, so the non-root indexer could not write it | `/target` created in the image with the right owner (Docker copies it into new volumes) |
| 4 | `seed --demo` stamps history with the index version but had no index mounted | The seed service mounts the index volume read-only |
| 5 | A new `.env` against an old database volume fails with "password authentication failed" | `docker-up` detects it and says to run `docker-down --volumes` |
| 6 | Uvicorn's access log duplicated the app's JSON request log in plain text | `--no-access-log` |
| 7 | `docker-logs.ps1 --tail N` read `N` as an unknown option (PowerShell `switch` falls through) | `break` in each matching branch |

## 4. Open issues

New: OI-37 (verified on stand-in base images). Updated: OI-33 (image scan wired, first
real run in CI), OI-35 (base images by tag; digests in Phase 10).

## 5. How this was verified

The sandbox has a Docker engine but cannot reach Docker Hub or GHCR. So local
**stand-ins** were built for each base image (Ubuntu 24.04 with Python 3.12, Node 26,
nginx running as UID 101 on 8080 with `/tmp` paths, PostgreSQL with the official
entrypoint's environment contract, busybox's `cp`), tagged with the real names, and the
Dockerfiles were built unchanged. Behaviour that depends on the real images (exact size,
Alpine's `wget`, PostgreSQL 18) is first exercised by CI's `images` job (OI-37).
