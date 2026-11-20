#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# seed.sh: create the admin account (SEED_ADMIN_EMAIL/PASSWORD) and, with --demo,
# reviewer/user accounts plus a week of demo query history and reviews (Phase 5).
# Migrates first, builds the index if --demo needs it. Parity: seed.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/seed.sh [--demo] [--reset] [--reset-password] [-h|--help]

  --demo             Also create reviewer@/user@ accounts and demo history (not in production)
  --reset            Empty the application tables first (not in production)
  --reset-password   Reset seeded accounts' passwords to SEED_ADMIN_PASSWORD

Accounts use the domain of SEED_ADMIN_EMAIL and the password SEED_ADMIN_PASSWORD.
USAGE
}

ARGS=(); DEMO=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo) ARGS+=("$1"); DEMO=1 ;;
    --reset|--reset-password) ARGS+=("$1") ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
require_cmd uv "Run scripts/setup.sh first."
load_dotenv
INDEX="${INDEX_DIR:-artifacts/index}"; [[ "$INDEX" = /* ]] || INDEX="$REPO_ROOT/$INDEX"

log_step "Migrate"
run uv run --directory "$BACKEND_DIR" python scripts/db.py upgrade
if [[ $DEMO -eq 1 && ! -f "$INDEX/manifest.json" ]]; then
  log_step "Build index (demo answers need it)"
  run uv run --directory "$BACKEND_DIR" python scripts/pipeline.py build
fi
log_step "Seed"
run uv run --directory "$BACKEND_DIR" python scripts/seed.py "${ARGS[@]}"
