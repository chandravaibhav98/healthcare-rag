#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# gen-client.sh: export the OpenAPI snapshot from the backend, then regenerate the
# frontend's TypeScript API types from it (Phase 6). Parity: gen-client.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/gen-client.sh [--check] [-h|--help]

  --check   Fail if backend/openapi.json or the generated TS types are stale (CI)
USAGE
}

CHECK=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) CHECK=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
require_cmd uv "Run scripts/setup.sh first."
require_cmd npm "Run scripts/setup.sh first."
if ((CHECK)); then
  log_step "Contract snapshots and API types are current"
  run uv run --directory "$BACKEND_DIR" python scripts/export_schemas.py --check
  run npm --prefix "$FRONTEND_DIR" run -s gen:api:check
else
  log_step "Export backend/openapi.json"
  run uv run --directory "$BACKEND_DIR" python scripts/export_schemas.py
  log_step "Generate frontend/src/api/generated/schema.d.ts"
  run npm --prefix "$FRONTEND_DIR" run -s gen:api
fi
