#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# clean.sh: remove build outputs and reports. Parity: clean.ps1.
# Default: reports and test output only. The index and the local database stay.
# --all: also artifacts/ (index, SQLite database, demo videos, submission bundles) and
# tool caches. Dependencies (.venv, node_modules) are untouched: see reset-env.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/clean.sh [--all] [--dry-run] [--ci] [-h|--help]

  --all       Also delete artifacts/ (index, local database, videos, bundles) and caches
  --dry-run   List what would be deleted
  --ci        Plain output (no colours)
USAGE
}

ALL=0; DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) ALL=1 ;;
    --dry-run) DRY=1 ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

TARGETS=(
  "$BACKEND_DIR/evaluation/reports" "$BACKEND_DIR/coverage.xml" "$BACKEND_DIR/coverage.json"
  "$BACKEND_DIR/.coverage" "$BACKEND_DIR/htmlcov"
  "$FRONTEND_DIR/dist" "$FRONTEND_DIR/coverage"
  "$E2E_DIR/test-results" "$E2E_DIR/playwright-report"
  "$REPO_ROOT/artifacts/e2e" "$REPO_ROOT/artifacts/load" "$REPO_ROOT/artifacts/k8s-verify"
  "$REPO_ROOT/artifacts/demo/run"
)
if ((ALL)); then
  TARGETS+=("$REPO_ROOT/artifacts" "$BACKEND_DIR/.pytest_cache" "$BACKEND_DIR/.mypy_cache"
    "$BACKEND_DIR/.ruff_cache" "$BACKEND_DIR/.hypothesis")
fi

log_step "Cleaning$( ((ALL)) && echo " (all)")"
removed=0
for t in "${TARGETS[@]}"; do
  [[ -e "$t" ]] || continue
  removed=$((removed + 1))
  if ((DRY)); then log_info "would delete ${t#"$REPO_ROOT/"}"; else rm -rf "$t"; log_info "deleted ${t#"$REPO_ROOT/"}"; fi
done
((removed)) || log_info "nothing to delete"
log_ok "done"
