#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# db-migrate.sh: apply Alembic migrations to DATABASE_URL (Phase 5).
# The API never migrates on startup (replicas would race); run this first.
# Parity: db-migrate.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/db-migrate.sh [--revision REV] [--downgrade REV] [--current] [-h|--help]

  (no option)          Upgrade to the latest revision (head)
  --revision REV       Upgrade to REV instead of head
  --downgrade REV      Downgrade to REV (e.g. -1 or base). Refused in production.
  --current            Show the database revision; exit 1 if it is not at head

DATABASE_URL comes from the environment or .env (see .env.example).
USAGE
}

CMD=(upgrade)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --revision) [[ $# -ge 2 ]] || die "--revision needs a value"; CMD=(upgrade --revision "$2"); shift ;;
    --downgrade) [[ $# -ge 2 ]] || die "--downgrade needs a value"; CMD=(downgrade "$2"); shift ;;
    --current) CMD=(current) ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
require_cmd uv "Run scripts/setup.sh first."
load_dotenv
log_step "Database migrations: ${CMD[*]}"
run uv run --directory "$BACKEND_DIR" python scripts/db.py "${CMD[@]}"
