#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# setup.sh: take a clean machine to "lint and tests green" (Phase 0 exit criterion).
#
#   1. preflight     toolchain and repository hygiene (scripts/preflight.sh)
#   2. .env          created from .env.example if missing (never overwritten)
#   3. backend       uv sync --locked   (exact versions from backend/uv.lock)
#   4. frontend      npm ci             (exact versions from frontend/package-lock.json)
#   5. git hooks     pre-commit install (skipped with --ci / --skip-hooks)
#   6. playwright    e2e/ dependencies + Chromium (system deps too with --ci)
#   7. verify        scripts/lint.sh + scripts/test.sh (skip with --no-verify)
#
# Idempotent: safe to re-run at any time. Parity: scripts/setup.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/setup.sh [--ci] [--skip-playwright] [--skip-hooks] [--no-verify] [-h|--help]

  --ci               Non-interactive CI mode: plain output, no .env, no git hooks
  --skip-playwright  Do not install Playwright browsers
  --skip-hooks       Do not install the pre-commit git hooks
  --no-verify        Skip the final lint + test run
USAGE
}

CI_MODE=0; SKIP_PLAYWRIGHT=0; SKIP_HOOKS=0; VERIFY=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ci) CI_MODE=1; SKIP_HOOKS=1; export NO_COLOR=1; init_colors ;;
    --skip-playwright) SKIP_PLAYWRIGHT=1 ;;
    --skip-hooks) SKIP_HOOKS=1 ;;
    --no-verify) VERIFY=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
CI_FLAG=(); ((CI_MODE)) && CI_FLAG=(--ci)

log_step "1/7 Pre-flight checks"
bash "$REPO_ROOT/scripts/preflight.sh" "${CI_FLAG[@]}" || die "Pre-flight failed: fix the [FAIL] items above, then re-run."

log_step "2/7 Environment file"
if ((CI_MODE)); then
  log_info "CI mode: using code defaults and CI-provided variables (no .env)."
elif [[ -f "$REPO_ROOT/.env" ]]; then
  log_ok ".env already exists (left untouched)"
else
  cp "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"
  log_ok "created .env from .env.example"
fi

log_step "3/7 Backend dependencies (uv)"
run uv sync --locked --directory "$BACKEND_DIR"
log_ok "backend/.venv matches backend/uv.lock"

log_step "4/7 Frontend dependencies (npm)"
run npm ci --prefix "$FRONTEND_DIR" --no-audit --no-fund
log_ok "frontend/node_modules matches frontend/package-lock.json"

log_step "5/7 Git hooks (pre-commit)"
if ((SKIP_HOOKS)); then
  log_info "skipped"
elif git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  run uv run --directory "$BACKEND_DIR" pre-commit install
  log_ok "pre-commit hooks installed"
else
  log_warn "not a Git repository; skipping hook installation"
fi

log_step "6/7 Playwright browsers"
if ((SKIP_PLAYWRIGHT)); then
  log_info "skipped (--skip-playwright)"
else
  run npm ci --prefix "$E2E_DIR" --no-audit --no-fund
  # --with-deps installs OS libraries via the package manager (sudo on Linux), so only
  # CI asks for it; locally, CHROME_PATH can point at an existing Chrome instead.
  PW_ARGS=(chromium)
  ((CI_MODE)) && PW_ARGS=(--with-deps chromium)
  run npm --prefix "$E2E_DIR" exec -- playwright install "${PW_ARGS[@]}"
  log_ok "e2e/node_modules + Playwright Chromium installed"
fi

if ((VERIFY)); then
  log_step "7/7 Verify: lint + tests"
  bash "$REPO_ROOT/scripts/lint.sh" "${CI_FLAG[@]}"
  bash "$REPO_ROOT/scripts/test.sh" --all "${CI_FLAG[@]}"
else
  log_step "7/7 Verify: skipped (--no-verify)"
fi

printf '\n%sSetup complete.%s Next: scripts/lint.sh · scripts/test.sh · see README.md\n' "$C_GREEN" "$C_OFF"
