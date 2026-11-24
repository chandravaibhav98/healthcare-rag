> Part of the [documentation index](../README.md#documentation). Synthetic corpus only; not for clinical use.

# Scripts

Operational automation lives in `scripts/`. Every script exists as `name.sh` (bash,
including Git Bash on Windows) and `name.ps1` (PowerShell 7+) with the same flags. All
support `--help`, are idempotent, and exit non-zero on failure.

## 1. Conventions

- Shared helpers: `scripts/lib/common.sh` / `Common.psm1` (logging, prerequisite checks,
  `.env` loading, repo-root detection) and `containers.sh` / `Containers.psm1`
  (image build and load, HTTP waits).
- On Windows Git Bash, the repo root is converted to `C:/…` form so native tools (Docker,
  kind) receive valid paths.
- `scripts/` is the source of truth; any Makefile or CI step only calls these scripts.

## 2. Catalogue

| Script | Purpose | Main flags |
| --- | --- | --- |
| `preflight` | Read-only toolchain and repository hygiene check | — |
| `setup` | Clean machine → lint and tests green | `--ci`, `--skip-hooks`, `--no-verify` |
| `reset-env` | Rebuild `.venv` and `node_modules` from the lockfiles | `--yes` |
| `clean` | Delete reports | `--all` (also `artifacts/` and caches) |
| `lint` | ruff, mypy, contract snapshots, eslint, prettier, tsc | `--fix` |
| `test` | pytest, Vitest, Playwright | `--backend --frontend --e2e --all --coverage` |
| `build-index` | Build and verify the index from `corpus/` | `--inspect`, `--out` |
| `verify-determinism` | N isolated rebuilds with different hash seeds must be byte-identical (SC1) | `--runs N` |
| `eval` | Evaluation scorecard (SC2, SC3, false validations, analyst list) | `--split`, `--gate` |
| `reproduce` | Every metric + E2E + demo from a fresh clone, compared with the records | — |
| `dev` | API (uvicorn reload) and web (Vite) together | `--api-only`, `--web-only` |
| `smoke` | Health, both `/qa` paths, schema | `--base-url`, `--bench N` |
| `db-migrate` | Alembic migrations | `--revision`, `--downgrade`, `--current` |
| `seed` | Admin account; demo users and history | `--demo`, `--reset` |
| `load-test` | k6 against `/qa` | `--vus`, `--duration`, `--target` |
| `security-scan` | pip-audit, npm audit, bandit, gitleaks, trivy | `--images` |
| `gen-client` | Export `openapi.json`, regenerate frontend API types | `--check` |
| `docker-up` / `docker-down` / `docker-rebuild` / `docker-logs` | Compose stack | `--demo`, `--observability`, `--volumes` |
| `k8s-up` / `k8s-down` / `k8s-status` / `k8s-port-forward` | kind + Envoy Gateway | `--recreate`, `--overlay` |
| `k8s-verify` | Zero failed requests during rolling restart and index rollout/rollback | — |
| `demo-record` | Cold start → narrated 1080p MP4 | `--gif`, `--target`, `--password` |
| `github-protect` | Apply branch and tag rulesets with the GitHub CLI | `--dry-run` |

## 3. CI helpers (`scripts/ci/`)

| Script | Purpose |
| --- | --- |
| `image-size.sh <image> <max MB>` | Sum layer sizes and fail over budget (Docker Desktop's containerd store over-reports `.Size`) |
| `save-images.sh` / `load-images.sh` | Pass built images between CI jobs |
| `publish-images.sh` | Push to GHCR with `sha-<commit>`, `main` and index tags |
| `release.sh` | Promote a commit's images to a release tag; render the prod overlay |

See [`scripts/ci/README.md`](../scripts/ci/README.md) and [releasing.md](releasing.md).
