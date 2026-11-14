#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# lint.sh: static checks (the same ones CI and pre-commit run).
#   backend : ruff check · ruff format --check · mypy --strict · contract snapshots
#   frontend: eslint · prettier --check · tsc --noEmit
# Runs every check and then reports all failures. Parity: scripts/lint.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/lint.sh [--backend] [--frontend] [--fix] [--ci] [-h|--help]

  --backend    Only lint the backend (default: both)
  --frontend   Only lint the frontend (default: both)
  --fix        Apply safe auto-fixes (ruff --fix, ruff format, eslint --fix, prettier --write)
  --ci         Plain output (no colours)
USAGE
}

DO_BACKEND=0; DO_FRONTEND=0; FIX=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend) DO_BACKEND=1 ;;
    --frontend) DO_FRONTEND=1 ;;
    --fix) FIX=1 ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
if ((DO_BACKEND == 0 && DO_FRONTEND == 0)); then DO_BACKEND=1; DO_FRONTEND=1; fi

if ((DO_BACKEND)); then
  require_cmd uv "Run scripts/setup.sh first."
  log_step "Backend lint"
  if ((FIX)); then
    run_step "ruff fix" uv run --directory "$BACKEND_DIR" ruff check --fix .
    run_step "ruff format" uv run --directory "$BACKEND_DIR" ruff format .
  else
    run_step "ruff check" uv run --directory "$BACKEND_DIR" ruff check .
    run_step "ruff format --check" uv run --directory "$BACKEND_DIR" ruff format --check .
  fi
  run_step "mypy --strict" uv run --directory "$BACKEND_DIR" mypy
  run_step "contract snapshots current" uv run --directory "$BACKEND_DIR" python scripts/export_schemas.py --check
fi

if ((DO_FRONTEND)); then
  require_cmd npm "Run scripts/setup.sh first."
  log_step "Frontend lint"
  if ((FIX)); then
    run_step "eslint --fix" npm --prefix "$FRONTEND_DIR" run -s lint:fix
    run_step "prettier --write" npm --prefix "$FRONTEND_DIR" run -s format
  else
    run_step "eslint" npm --prefix "$FRONTEND_DIR" run -s lint
    run_step "prettier --check" npm --prefix "$FRONTEND_DIR" run -s format:check
  fi
  run_step "tsc --noEmit" npm --prefix "$FRONTEND_DIR" run -s typecheck
  run_step "API types current" npm --prefix "$FRONTEND_DIR" run -s gen:api:check
fi

finish_steps "Lint"
