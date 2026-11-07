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
| **Phase 2: retrieval and extractive QA core** | ✅ Hybrid RRF + expansion, 15/15 smoke hit@5 ([report](docs/project/phase-2-report.md)) |
| Phase 3: validation engine and `/qa` API | ⏭️ Next |

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

## API contract v1

`POST /api/v1/qa` (alias `POST /qa`). Request `{ "question": str, "top_k": 1–20 }`.
Response `{ answer, citations, confidence, status ∈ {validated, needs_review}, meta? }`.
Errors are RFC 9457 `application/problem+json`. The committed snapshot is
[`backend/openapi.json`](backend/openapi.json). In Phase 0 the route validates requests
and returns `501`; the pipeline arrives in Phase 3.

## Repository layout

| Path | Contents |
| --- | --- |
| `backend/` | FastAPI app, RAG library, evaluation, tests ([README](backend/README.md)) |
| `frontend/` | React + TypeScript + Vite SPA |
| `corpus/` | 42 synthetic guideline documents ([corpus card](corpus/CORPUS_CARD.md)) |
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

More scripts arrive with later phases (`plan.md` §5).

## Configuration

All settings come from environment variables or `.env`. Every key is documented in
[`.env.example`](.env.example) and validated by `backend/app/core/config.py`.

## Note on the UI

The brief lists an optional Streamlit UI. This project replaces it with a React SPA
(Phase 6) that includes an admin dashboard.
