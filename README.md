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
| **Phase 4: evaluation and threshold tuning** | ✅ Harness + CI gate. Held-out: SC3 met (0.807); SC2 P@5 0.417 vs ceiling 0.583 (decision pending); 2/12 false validations ([report](docs/project/phase-4-report.md), [evaluation](docs/evaluation-report.md)) |
| Phase 5: persistence, auth and admin APIs | ⏭️ Next |

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
scripts/dev.sh --api-only        # API on http://127.0.0.1:8000, Swagger UI at /docs
scripts/smoke.sh                 # in a second terminal: probes, both /qa paths, schema
```

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/qa \
  -H 'Content-Type: application/json' \
  -d '{"question": "How long can a multi-dose vial be used after opening?", "top_k": 5}'
```

## API contract v1.1

`POST /api/v1/qa` (alias `POST /qa`). Request `{ "question": str, "top_k": 1–20 }`.
Response `{ answer, citations, confidence, status ∈ {validated, needs_review}, meta }`.

- `validated`: the answer is extracted from the cited guideline text, with `[n]` markers.
- `needs_review`: the answer is withheld and replaced by a fixed message; `citations`
  still lists up to 3 candidate sources and `meta.reason` says why
  (`no_evidence`, `below_retrieval_floor`, `numeric_mismatch`, `low_confidence`).
- `meta.signals` shows the evidence behind `confidence` (coverage, query support,
  retrieval score, numeric check; [ADR-0002](docs/adr/0002-composite-confidence-and-numeric-gate.md)).

Errors are RFC 9457 `application/problem+json` (422, 429, 500, 503) with a `request_id`
that matches the `X-Request-ID` response header. Operational endpoints: `GET /healthz`,
`GET /readyz`, `GET /version`, `GET /metrics` (Prometheus). The committed snapshot is
[`backend/openapi.json`](backend/openapi.json).

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/` | FastAPI app, RAG library, evaluation, tests ([README](backend/README.md)) |
| `frontend/` | React + TypeScript + Vite SPA |
| `corpus/` | 72 synthetic guideline documents ([corpus card](corpus/CORPUS_CARD.md)) |
| `e2e/` | Playwright E2E and demo (Phases 7 and 11) |
| `deploy/` | Docker, Compose, Kubernetes (Phases 8 and 9) |
| `scripts/` | Ops scripts, `.sh` + `.ps1` pairs ([CONTRIBUTING](CONTRIBUTING.md)) |
| `docs/` | ADRs, project docs, spikes |

## Scripts

| Script | Purpose |
| --- | --- |
| `preflight` | Read-only toolchain and repository hygiene check |
| `setup` | Clean machine → lint and tests green (`--ci`, `--skip-hooks`, `--no-verify`) |
| `lint` | ruff, mypy, contract snapshots, eslint, prettier, tsc (`--fix`) |
| `test` | pytest and vitest (`--backend`, `--frontend`, `--coverage`) |
| `build-index` | Build and verify the index from `corpus/` (`--inspect` for chunk statistics) |
| `verify-determinism` | SC1: N isolated rebuilds with different hash seeds must be byte-identical |
| `dev` | API (uvicorn `--reload`) and web (Vite) together (`--api-only`, `--web-only`) |
| `smoke` | Probe a running API; `--bench N` adds a p95 latency check (`--base-url`) |
| `eval` | Evaluation scorecard (SC2, SC3, false validations); `--gate` for CI, `--split test` once per frozen config |

More scripts arrive with later phases (`plan.md` §5).

## Configuration

All settings come from environment variables or `.env`. Every key is documented in
[`.env.example`](.env.example) and validated by `backend/app/core/config.py`.

## Note on the UI

The brief lists an optional Streamlit UI. This project replaces it with a React SPA
(Phase 6) that includes an admin dashboard.
