#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# test.sh: run the selected test layers. Parity: scripts/test.ps1.
#   backend : pytest (unit, property, integration, api, contract incl. Schemathesis)
#   frontend: vitest (+ coverage thresholds in vite.config.ts)
#   e2e     : Playwright functional suite (e2e/tests). Starts its own API + web
#             server unless E2E_BASE_URL points at a running stack.
#
# --coverage turns the coverage targets of plan §4 Phase 7 into a failing gate:
#   backend  app/rag ≥ 90 %, app/services ≥ 85 %, overall ≥ 80 % (scripts/coverage_gate.py)
#   frontend ≥ 70 % lines/statements/functions/branches (vitest thresholds)
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/test.sh [--backend] [--frontend] [--e2e] [--all] [--coverage] [--ci] [-h|--help]

  --backend    Backend tests (pytest)
  --frontend   Frontend tests (vitest)
  --e2e        Playwright functional E2E (e2e/tests)
  --all        Backend + frontend + E2E
  --coverage   Coverage reports AND gates (backend ≥80/85/90 %, frontend ≥70 %)
  --ci         Plain output (no colours)

  Default (no layer chosen): backend + frontend.
  E2E environment: CHROME_PATH (use an installed Chrome), E2E_BASE_URL (external stack).
USAGE
}

DO_BACKEND=0; DO_FRONTEND=0; DO_E2E=0; COVERAGE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend) DO_BACKEND=1 ;;
    --frontend) DO_FRONTEND=1 ;;
    --e2e) DO_E2E=1 ;;
    --all) DO_BACKEND=1; DO_FRONTEND=1; DO_E2E=1 ;;
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
    run_step "pytest (coverage)" uv run --directory "$BACKEND_DIR" pytest --cov \
      --cov-report=term --cov-report=xml --cov-report=json
    run_step "coverage gate" uv run --directory "$BACKEND_DIR" python scripts/coverage_gate.py coverage.json
  else
    run_step "pytest" uv run --directory "$BACKEND_DIR" pytest
  fi
fi

if ((DO_FRONTEND)); then
  require_cmd npm "Run scripts/setup.sh first."
  log_step "Frontend tests"
  if ((COVERAGE)); then
    # Thresholds live in vite.config.ts, so vitest itself fails below 70 %.
    run_step "vitest (coverage gate)" npm --prefix "$FRONTEND_DIR" run -s test:coverage
  else
    run_step "vitest" npm --prefix "$FRONTEND_DIR" run -s test
  fi
fi

if ((DO_E2E)); then
  require_cmd npm "Run scripts/setup.sh first."
  log_step "E2E tests (Playwright)"
  if [[ ! -d "$E2E_DIR/node_modules" ]]; then
    log_error "e2e/node_modules is missing: run scripts/setup.sh (or npm ci --prefix e2e)."
    STEP_FAILURES+=("e2e (not installed)")
  else
    run_step "playwright" npm --prefix "$E2E_DIR" run -s test
    log_info "HTML report: npm --prefix e2e run report"
  fi
fi

finish_steps "Tests"
