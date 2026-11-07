# Phase 0 Report — Foundations, Contracts & Decisions

- **Date:** 2026-11-07 · **Plan ref:** `plan.md` §4 Phase 0
- **Result:** every deliverable is built and verified. **Exit is blocked only on
  approval of ADR-0001 and ADR-0002** (mentor or stakeholder).

## 1. Deliverables

| # | Deliverable | Status | Where |
| --- | --- | --- | --- |
| 1 | Monorepo skeleton per §2.3, `.gitattributes`, `.editorconfig` | ✅ | `backend/ frontend/ corpus/ e2e/ deploy/ docs/ scripts/ .github/` |
| 2 | `backend/pyproject.toml` (exact pins) + `uv.lock`; `frontend/package.json` + lockfile | ✅ | `backend/`, `frontend/` |
| 3 | Pre-commit: ruff, ruff-format, mypy, eslint, prettier, EOF/whitespace fixers, detect-secrets | ✅ | `.pre-commit-config.yaml`, `.secrets.baseline` |
| 4 | `.env.example` with every config key documented | ✅ | `.env.example` ↔ `backend/app/core/config.py` (parity test) |
| 5 | `docs/adr/0001…0009` drafted | ✅ | `docs/adr/` |
| 6 | API contract v1 (Pydantic) + `openapi.json` snapshot | ✅ | `backend/app/api/schemas/`, `backend/openapi.json` |
| 7 | Gold-dataset schema | ✅ | `backend/evaluation/schemas.py`, `datasets/gold.schema.json`, `gold_example.jsonl` |
| 8 | `scripts/setup.*` + `scripts/lib/common.*` | ✅ | plus `lint.*` and `test.*`, which setup and CI both call |
| 9 | CI skeleton: lint + typecheck + unit tests on every PR | ✅ | `.github/workflows/ci.yml` (Ubuntu + Windows matrix, plus a hygiene job) |
| 10 | README with purpose and synthetic-corpus disclaimer | ✅ | `README.md` |

**Exit criteria**

| Criterion | Status |
| --- | --- |
| `setup.sh` and `setup.ps1` take a clean machine to "lint and tests green" | ✅ Verified from fresh clones (§2). Your own Windows run is still to be confirmed (§5) |
| ADR-0001 and ADR-0002 approved | ⏳ **Pending.** Send readiness Q1 and Q2 together with both ADRs |

## 2. Verification evidence

Run in a Linux VM on fresh `git clone`s (no `.venv`, no `node_modules`), using
Python 3.12.15, Node 26.7.0, npm 11.19 and PowerShell 7.4.6.

| Check | Result |
| --- | --- |
| `bash scripts/setup.sh --ci` (fresh clone) | exit 0: preflight READY, `uv sync --locked`, `npm ci`, all lint checks, all tests |
| `pwsh scripts/setup.ps1 --ci` (separate fresh clone) | exit 0, identical steps and results |
| `bash scripts/setup.sh` developer mode, run twice | exit 0 both times: `.env` created once, pre-commit hooks installed, idempotent |
| Backend lint | ruff ✔ · ruff format ✔ · `mypy --strict` (32 files) ✔ · contract snapshots current ✔ |
| Backend tests | **60 passed** (contract invariants, config parity and guards, gold schema, API routes, snapshots) |
| Frontend | eslint (strict type-checked, `--max-warnings=0`) ✔ · prettier ✔ · `tsc --noEmit` ✔ · vitest 2 passed |
| Failure path | planted ruff + TS errors → `lint.sh` and `lint.ps1` both exit 1 and list **all** failing checks; unknown flags exit 2 |
| `pre-commit run --all-files` | every hook Passed, including detect-secrets, case conflicts and the local mypy and contract hooks |
| `actionlint` on `ci.yml` | 0 findings |
| Line endings | all 104 tracked files stored as LF in the index |
| OpenAPI | 3.1.0; both routes; 422 and 501 declared as `application/problem+json` only |

Not yet verified: the workflow running on GitHub itself. The Windows matrix leg will be
the first true Windows-native run of the scripts after your own (§5).

## 3. Decisions and deviations made during Phase 0

| Topic | What changed or was decided | Why |
| --- | --- | --- |
| **Relevant chunks per question** | ADR-0001 sets **≥ 4** (the plan said ≥ 3) | 3 relevant chunks cap P@5 at 0.60, below the 0.65 target. Corrected before annotation starts |
| TypeScript | Held at **6.0.3** (latest is 7.0.2) | `typescript-eslint` 8.72 supports `typescript < 6.1`. Recorded in CONTRIBUTING |
| Test HTTP client | `httpx2` instead of `httpx` | Starlette's TestClient now deprecates `httpx`. Caught by `filterwarnings = error` |
| `/qa` in Phase 0 | Real routes that validate input and return **501 problem+json** | Contract-first: the snapshot, the generated client and the tests target the real v1 shape now |
| Errors | All 4xx/5xx are RFC 9457; 422 does not echo input | ADR-0006 + ADR-0009 (PHI) |
| Gold schema | Adds `topic` and `kind` to the plan's field list | Needed for the stratified split and per-kind reporting in Phase 4 |
| Chunk IDs | `doc::section-slug::NNNN` (4-digit ordinal), defined once in `app/domain/ids.py` | Contract, chunker and gold set must agree, otherwise P@K silently reads 0 |
| Config | Unprefixed keys (matching the plan's names); production guards for the JWT secret, question logging and CORS `*` | Misconfiguration fails at start-up, not in an audit |
| Scripts | `lint.*` and `test.*` brought forward from §5 | `setup` and CI call them; scripts remain the single source of truth |

## 4. Risks updated

| Risk | Update |
| --- | --- |
| R1 (P@5 unreachable) | Mitigated by ADR-0001 (≥ 4 relevant chunks, reported ceiling). Pending approval |
| R2 (trivial coverage) | Mitigated by ADR-0002 (composite score with worked examples). Pending approval |
| R4 (cross-platform) | CI now runs the full setup on Windows for every PR |
| R9 (PHI in logs) | Partly implemented: input never echoed; production rejects question logging |

## 5. Your actions to close Phase 0

1. **Review and commit** (suggested split, Conventional Commits):
   `chore: monorepo skeleton and tooling` → `feat(api): contract v1 and openapi snapshot`
   → `feat(eval): gold dataset schema` → `docs(adr): draft ADR-0001…0009`, or a single commit
   `feat: phase 0 foundations`.
2. Rename the plan to the documented name (case-only renames need `git mv` on Windows):
   `git mv -f Plan.md plan.md`
3. Run `pwsh ./scripts/setup.ps1` once on Windows (developer mode installs the git hooks).
4. Push to GitHub and confirm both `quality` legs and the `hygiene` job are green.
5. Get ADR-0001 and ADR-0002 approved, fill in their Approval tables, and set their status to *Accepted*.

## 6. Hand-off to Phase 1

Phase 1 can start before the approvals arrive, because corpus authoring and the index
build do not depend on them. Corpus authoring should already follow ADR-0001: core-topic
sections long enough to yield ≥ 4 chunks each.
