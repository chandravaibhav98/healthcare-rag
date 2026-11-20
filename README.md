# Healthcare Guidelines RAG Assistant — Rapid Query & Validation System

> ⚠️ **Not for clinical use.** All guideline content in this repository is **synthetic**
> (WHO/NIH/CDC-*style*, not real guidance). This is an engineering prototype. Never use
> its output to make patient-care decisions.

A citation-first question-answering service over guideline documents. It answers
**only** from retrieved evidence, scores every answer for support, and **abstains**
(`status: needs_review`) when that support is weak. The synthetic corpus can later be
replaced by an organisation's secure guideline repository.

## Status

| Stage | State |
| --- | --- |
| Pre-Phase 0: initialisation | ✅ [readiness report](docs/project/phase-0-readiness.md) |
| Phase 0: foundations, contracts and decisions | ✅ Built and verified · ⏳ ADR-0001 and ADR-0002 awaiting approval ([report](docs/project/phase-0-report.md)) |
| Phase 1: synthetic corpus and deterministic indexing | ✅ 42 docs, 209 chunks, byte-identical rebuilds ([report](docs/project/phase-1-report.md)) |
| Phase 2: retrieval and extractive QA core | ✅ Hybrid RRF + expansion, 15/15 smoke hit@5 ([report](docs/project/phase-2-report.md)) |
| Phase 3: validation engine and `/qa` API | ✅ Live `/qa`, abstention, probes, metrics; p95 ≈ 11 ms over HTTP ([report](docs/project/phase-3-report.md)) |
| Phase 4: evaluation and threshold tuning | ✅ Harness + CI gate. Held-out: SC3 met (0.807); SC2 P@5 0.417 vs ceiling 0.583 (decision pending); 2/12 false validations ([report](docs/project/phase-4-report.md), [evaluation](docs/evaluation-report.md)) |
| Phase 5: persistence, auth and admin APIs | ✅ SQLite/PostgreSQL, JWT + RBAC, 17 admin routes, audited runtime tuning, PHI redaction + retention ([report](docs/project/phase-5-report.md)) |
| Phase 6: React assistant and admin dashboard | ✅ Assistant with evidence view and escalation, 7-section dashboard; Lighthouse a11y 100 on every route, axe clean in light and dark ([report](docs/project/phase-6-report.md)) |
| Phase 7: test hardening and quality gates | ✅ Coverage gates (backend 93 %, frontend 92 % lines), Schemathesis on every operation, 20 Playwright journeys + axe gate, k6 50 VUs × 5 min p95 179 ms / 0 % 5xx, security scans ([report](docs/project/phase-7-report.md)) |
| Phase 8: containerization | ✅ Three hardened images (API, web, index), Compose stack with internal network and observability profile; E2E 20/20 and k6 through nginx ([report](docs/project/phase-8-report.md)) |
| **Phase 9: Kubernetes** | ✅ Kustomize base + local/prod overlays, Gateway API, restricted Pod Security, NetworkPolicies, HPA/PDB; E2E 20/20 through the gateway; zero failed requests during rolling restart and index rollback ([report](docs/project/phase-9-report.md)) |
| Phase 10: CI/CD pipeline | ⏭️ Next |

## Quick start

Prerequisites: Git, [uv](https://docs.astral.sh/uv/), Node 26 (`.nvmrc`; e.g. via `fnm`),
PowerShell 7+ on Windows. Check with `scripts/preflight.*`.

```bash
scripts/setup.sh                 # Git Bash (primary on Windows), Linux, macOS
```

PowerShell twins exist for every script (`pwsh ./scripts/setup.ps1`). See
[`docs/project/working-agreements.md`](docs/project/working-agreements.md) for the Git Bash setup.

`setup` checks the toolchain, creates `.env`, installs the locked dependencies, installs
the pre-commit hooks, and finishes by running every lint check and test.

Run the whole stack in containers instead (Docker only; details in [deploy/README.md](deploy/README.md)):

```bash
scripts/docker-up.sh --demo      # Compose: http://localhost:8080
scripts/k8s-up.sh                # kind + Envoy Gateway: http://localhost:8088 (needs kind, kubectl)
```

## Architecture (target)

```text
React SPA ──HTTPS/JSON──► FastAPI (stateless) ──► RAG domain library
 assistant + admin          /api/v1/qa (+ /qa)       retrieve (FAISS ⊕ BM25, RRF)
                            problem+json errors      → extract answer → validate
                                   │                 → validated | needs_review
                                   ▼
                     PostgreSQL (logs, reviews)   Versioned index artifact (offline build)
```

Details: [`plan.md`](plan.md) §2 · decisions: [`docs/adr/`](docs/adr/README.md).

## Run it

```bash
scripts/build-index.sh           # once, and after any corpus change
scripts/seed.sh --demo           # migrate the database, admin + demo accounts and history
scripts/dev.sh                   # API on :8000 (Swagger at /docs) + web app on http://localhost:5173
scripts/smoke.sh                 # in a second terminal: probes, both /qa paths, schema
```

The default `DATABASE_URL` is a local SQLite file (`artifacts/app.db`). Demo accounts are
`admin@example.org`, `reviewer@example.org` and `user@example.org`, all with
`SEED_ADMIN_PASSWORD` (dev default `change-me-admin`). Leave `DATABASE_URL` empty to run
`/qa` stateless.

> **Upgrading from Phase 4?** An existing `.env` may still point `DATABASE_URL` at
> PostgreSQL on `localhost:5432`. Copy the new `DATABASE_URL`, `SEED_ADMIN_*` and Phase 5
> keys from `.env.example`, or empty `DATABASE_URL`. (The Compose and Kubernetes stacks
> bring their own PostgreSQL.)

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/qa \
  -H 'Content-Type: application/json' \
  -d '{"question": "How long can a multi-dose vial be used after opening?", "top_k": 5}'
```

## API contract v1.3

`POST /api/v1/qa` (alias `POST /qa`). Request `{ "question": str, "top_k": 1–20 }`.
Response `{ answer, citations, confidence, status ∈ {validated, needs_review}, meta }`.

- `validated`: the answer is extracted from the cited guideline text, with `[n]` markers.
- `needs_review`: the answer is withheld and replaced by a fixed message; `citations`
  still lists up to 3 candidate sources and `meta.reason` says why
  (`no_evidence`, `below_retrieval_floor`, `numeric_mismatch`, `low_confidence`).
- `meta.signals` shows the evidence behind `confidence` (coverage, query support,
  retrieval score, numeric check; [ADR-0002](docs/adr/0002-composite-confidence-and-numeric-gate.md)).

Errors are RFC 9457 `application/problem+json` (401, 403, 404, 409, 422, 429, 500, 503) with a `request_id`
that matches the `X-Request-ID` response header. Operational endpoints: `GET /healthz`,
`GET /readyz`, `GET /version`, `GET /metrics` (Prometheus). The committed snapshot is
[`backend/openapi.json`](backend/openapi.json).

Since 1.2 and 1.3 (all additive):

- **Auth** `POST /api/v1/auth/login`, `/refresh` (rotating, httpOnly cookie), `/logout`,
  `GET /api/v1/auth/me`. `/qa` accepts an optional bearer token and answers 401 only when
  `ALLOW_ANONYMOUS_QA=false`.
- **Admin** under `/api/v1/admin` (reviewer or admin; [RBAC matrix](docs/adr/0008-persistence-auth-index-distribution.md)):
  `stats`, `queries`, `reviews` (+ gold JSONL export), `eval-runs`, `index/versions`,
  `index/rebuild` (development only), `documents`, `config` (audited runtime threshold and
  weights), `audit-log`. Lists share one envelope `{items, total, limit, offset}` with
  `limit`, `offset`, `sort`, `order`.
- **Escalation** (1.3) `POST /api/v1/escalations` `{request_id, note}`: a user asks a
  reviewer to check an answer; it joins the review queue. `stats` gained a confidence
  histogram.
- **1.3.1** (Phase 7, from contract fuzzing): optional authentication is declared in the
  OpenAPI document, list `sort` parameters are enums, `offset` is capped at 1,000,000,
  and malformed JSON (400) and every error media type are documented.

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/` | FastAPI app, RAG library, evaluation, tests ([README](backend/README.md)) |
| `frontend/` | React + TypeScript + Vite SPA |
| `corpus/` | 72 synthetic guideline documents ([corpus card](corpus/CORPUS_CARD.md)) |
| `e2e/` | Playwright E2E + accessibility gate, k6 load test, Phase 6 audit, demo (Phase 11) ([README](e2e/README.md)) |
| `deploy/` | Dockerfiles, Compose, Kubernetes manifests ([README](deploy/README.md)) |
| `scripts/` | Ops scripts, `.sh` + `.ps1` pairs ([CONTRIBUTING](CONTRIBUTING.md)) |
| `docs/` | ADRs, project docs, spikes |

## Scripts

| Script | Purpose |
| --- | --- |
| `preflight` | Read-only toolchain and repository hygiene check |
| `setup` | Clean machine → lint and tests green (`--ci`, `--skip-hooks`, `--no-verify`) |
| `lint` | ruff, mypy, contract snapshots, eslint, prettier, tsc (`--fix`) |
| `test` | pytest, vitest, Playwright (`--backend`, `--frontend`, `--e2e`, `--all`); `--coverage` enforces the coverage gates |
| `load-test` | k6 against `/qa`: 50 VUs × 5 min, p95 < 300 ms, 0 % 5xx (`--vus`, `--duration`, `--target`) |
| `security-scan` | pip-audit, npm audit, bandit, gitleaks, trivy fs; `--images` scans the three images (`--strict`, `--only`) |
| `build-index` | Build and verify the index from `corpus/` (`--inspect` for chunk statistics) |
| `verify-determinism` | SC1: N isolated rebuilds with different hash seeds must be byte-identical |
| `dev` | API (uvicorn `--reload`) and web (Vite) together (`--api-only`, `--web-only`) |
| `smoke` | Probe a running API; `--bench N` adds a p95 latency check (`--base-url`) |
| `eval` | Evaluation scorecard (SC2, SC3, false validations); `--gate` for CI, `--split test` once per frozen config |
| `db-migrate` | Alembic migrations for `DATABASE_URL` (`--revision`, `--downgrade`, `--current`) |
| `seed` | Migrate, then the admin account; `--demo` adds reviewer/user accounts and a week of history (`--reset`, `--reset-password`) |
| `docker-up` / `docker-down` / `docker-rebuild` / `docker-logs` | The Compose stack on http://localhost:8080 (`--demo`, `--observability`, `--volumes`) |
| `k8s-up` / `k8s-down` / `k8s-status` / `k8s-port-forward` | kind + Envoy Gateway on http://localhost:8088 (`--recreate`, `--existing-cluster`, `--overlay prod` renders only) |
| `k8s-verify` | Zero failed requests during a rolling restart and an index rollout/rollback under k6 load |
| `gen-client` | Export `backend/openapi.json` and regenerate the frontend's TypeScript API types (`--check` for CI) |

More scripts arrive with later phases (`plan.md` §5).

## Configuration

All settings come from environment variables or `.env`. Every key is documented in
[`.env.example`](.env.example) and validated by `backend/app/core/config.py`.

## The web app

![Query Assistant: validated answer with the evidence panel](docs/project/phase-6-ui/assistant-validated.png)

- **Query Assistant** (`/`): ask with Enter, choose `top_k`; the answer card shows the
  status badge, a confidence meter with the signal breakdown, and `[n]` citation chips.
  The evidence panel shows the cited chunk with the words it shares with the answer
  highlighted and every number checked. Abstentions explain why, list the closest
  sources and offer **Escalate for review**. Session history, copy with sources, and a
  permanent "not for clinical use" banner.
- **Dashboard** (`/admin`, reviewer or admin): overview KPIs and charts, review queue
  (side-by-side evidence, approve/reject/correct, promote to gold), query explorer
  with a detail drawer, evaluation runs with the threshold sweep and low-confidence
  list, index versions and corpus inventory, audited settings with an impact preview,
  and the audit log (admin).
- Dark mode, responsive down to 390 px, WCAG 2.2 AA (Lighthouse accessibility 100 on
  every route). Details: [frontend/README.md](frontend/README.md).

The brief lists an optional Streamlit UI. This React SPA replaces it.
