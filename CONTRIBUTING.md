# Contributing

> **Primary shell: Git Bash.** Commands in all docs use bash syntax; the `.ps1` twins are kept
> for parity and run in CI. See [`docs/project/working-agreements.md`](docs/project/working-agreements.md).

## Workflow: trunk-based

- `main` is always releasable and protected. CI (`.github/workflows/ci.yml`) must be green.
- Work on **short-lived branches** (at most a few days), named `<type>/<short-topic>`,
  e.g. `feat/hybrid-retrieval`, `fix/chunker-tables`, `docs/adr-0003`.
- Open a PR early. **Squash-merge** with a Conventional Commit title.
- PRs that implement or change an architectural decision reference the ADR
  (`Implements ADR-0004`). A changed decision needs a **new** ADR that supersedes the old one.

## Commit messages: Conventional Commits

```text
<type>(<scope>): <imperative summary, ≤ 72 chars>

[optional body: what and WHY]
[optional footer: Refs ADR-0002 · BREAKING CHANGE: ...]
```

| type | use for |
| --- | --- |
| `feat` | user-visible capability |
| `fix` | bug fix |
| `docs` | docs and ADRs only |
| `test` | tests only |
| `refactor` | no behaviour change |
| `perf` | performance |
| `build` | dependencies, lockfiles, packaging |
| `ci` | workflows |
| `chore` | repo maintenance |

Scopes: `api`, `rag`, `eval`, `corpus`, `config`, `frontend`, `scripts`, `deploy`, `docs`.
Example: `feat(rag): add RRF fusion with chunk_id tie-break`.

## Scripts are the source of truth

Every routine task goes through `scripts/` (bash `*.sh` and PowerShell `*.ps1`, with
identical flags). CI calls the same scripts, so "green locally" means "green in CI".

| Task | Command |
| --- | --- |
| First-time setup (idempotent) | `scripts/setup.sh` · `pwsh scripts/setup.ps1` |
| Lint + typecheck (+ `--fix`) | `scripts/lint.sh` · `pwsh scripts/lint.ps1` |
| Tests (`--backend`, `--frontend`, `--coverage`) | `scripts/test.sh` · `pwsh scripts/test.ps1` |
| Environment check | `scripts/preflight.sh` · `pwsh scripts/preflight.ps1` |
| Run API + web locally | `scripts/dev.sh` · `pwsh scripts/dev.ps1` |
| Smoke-test a running API (+ `--bench N`) | `scripts/smoke.sh` · `pwsh scripts/smoke.ps1` |
| Evaluation scorecard and regression gate | `scripts/eval.sh` · `pwsh scripts/eval.ps1` |
| Database migrations (never at API start-up) | `scripts/db-migrate.sh` · `pwsh scripts/db-migrate.ps1` |
| Admin account and demo data | `scripts/seed.sh --demo` · `pwsh scripts/seed.ps1 --demo` |

A new script must ship as a `.sh` + `.ps1` pair, support `--help`, be idempotent, and
return non-zero on failure. Shared helpers live in `scripts/lib/`.

## Quality gates (pre-commit + CI)

- Backend: `ruff check`, `ruff format`, `mypy --strict`, `pytest`, contract snapshot check.
- Frontend: `eslint` (type-checked, zero warnings), `prettier --check`, `tsc --noEmit`, `vitest`.
- Hygiene: trailing whitespace, final newline, LF line endings, case conflicts, large
  files, private keys, `detect-secrets` (baseline: `.secrets.baseline`).
- Hooks never rewrite `corpus/`: its bytes define `index_version` (SC1).

## Contracts

- `backend/openapi.json` and `backend/evaluation/datasets/gold.schema.json` are
  **committed snapshots**. After changing a schema, run
  `uv run --directory backend python scripts/export_schemas.py` and commit the diff.
  Explain it in the PR, because a contract change is a product decision.
- A change to `backend/app/db/models.py` needs an Alembic migration
  (`uv run --directory backend alembic revision --autogenerate -m "..."`, then review it).
  `tests/integration/test_migrations.py` fails when models and migrations drift.
- `.env.example` must list every `Settings` field, each with a comment (enforced by a test).

## Dependencies

- Python: exact pins in `backend/pyproject.toml` plus `uv.lock`
  (`uv add --directory backend "pkg==X.Y.Z"`). Keep the ruff version in
  `.pre-commit-config.yaml` equal to the one in `pyproject.toml`.
- Frontend: exact versions (`.npmrc save-exact=true`) plus `package-lock.json`. Node is pinned by `.nvmrc`.
- **TypeScript is held at 6.0.x**: `typescript-eslint` 8.x supports `typescript < 6.1`,
  and TypeScript 7 (the native port) is not supported yet. Re-evaluate when
  `typescript-eslint` adds TS 7 support.

- **npm `overrides`** (in `frontend/package.json`) force patched versions of transitive
  dependencies when the direct dependency has not released a fix yet. Each override is
  listed below with its advisory. Remove an override once upstream ships the fix.

  | Override | Reason | Remove when |
  | --- | --- | --- |
  | `minimatch` → `11.0.5` | GHSA-g3hv-75wg-m249 (moderate, ReDoS) in `minimatch <11.0.1`, pulled in by `eslint` 10 and `typescript-eslint` 8 (lint tooling only; not shipped in the app) | `eslint` and `typescript-eslint` depend on `minimatch >=11.0.1` |

## Never commit

`.env`, credentials or tokens, index artifacts (`artifacts/`, `*.faiss`), evaluation run
outputs, or real patient data of any kind.
