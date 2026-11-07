#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# test.sh: run the selected test layers. Parity: scripts/test.ps1.
#   backend : pytest (unit, api, contract; integration arrives in Phase 1+)
#   frontend: vitest
#   e2e     : Playwright (available from Phase 7)
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/test.sh [--backend] [--frontend] [--e2e] [--all] [--coverage] [--ci] [-h|--help]

  --backend    Backend tests (pytest)
  --frontend   Frontend tests (vitest)
  --e2e        Playwright E2E (Phase 7+; currently reports "not available")
  --all        Backend + frontend (default when no layer is chosen)
  --coverage   Backend coverage report (terminal + backend/coverage.xml)
  --ci         Plain output (no colours)
USAGE
}

DO_BACKEND=0; DO_FRONTEND=0; DO_E2E=0; COVERAGE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend) DO_BACKEND=1 ;;
    --frontend) DO_FRONTEND=1 ;;
    --e2e) DO_E2E=1 ;;
    --all) DO_BACKEND=1; DO_FRONTEND=1 ;;
    --coverage) COVERAGE=1 ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
if ((DO_BACKEND == 0 && DO_FRONTEND == 0 && DO_E2E == 0)); then DO_BACKEND=1; DO_FRONTEND=1; fi

if ((DO_BACKEND)); then
  require_cmd uv "Run scripts/setup.sh first."
  log_step "Backend tests"
  if ((COVERAGE)); then
    run_step "pytest (coverage)" uv run --directory "$BACKEND_DIR" pytest --cov --cov-report=term --cov-report=xml
  else
    run_step "pytest" uv run --directory "$BACKEND_DIR" pytest
  fi
fi

if ((DO_FRONTEND)); then
  require_cmd npm "Run scripts/setup.sh first."
  log_step "Frontend tests"
  run_step "vitest" npm --prefix "$FRONTEND_DIR" run -s test
fi

if ((DO_E2E)); then
  log_step "E2E tests"
  log_error "Playwright E2E is not available yet (plan Phase 7)."
  STEP_FAILURES+=("e2e (not available)")
fi

finish_steps "Tests"
