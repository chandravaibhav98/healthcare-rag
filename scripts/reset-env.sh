#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# reset-env.sh: delete the local environments and rebuild them from the lockfiles.
# Parity: reset-env.ps1. Removes backend/.venv, frontend/node_modules, e2e/node_modules,
# artifacts/ (with --keep-db the SQLite database stays) and caches, then runs
# scripts/setup.sh. .env is kept. Use it when a dependency update left a broken
# environment, or to prove a clean machine still reaches "lint and tests green".
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/reset-env.sh [--yes] [--keep-db] [--ci] [-h|--help] [-- setup flags]

  --yes       Do not ask for confirmation
  --keep-db   Keep artifacts/app.db (the local SQLite database)
  --ci        Plain output (no colours); implies --yes
  -- ...      Everything after -- is passed to scripts/setup.sh (e.g. -- --skip-playwright)
USAGE
}

YES=0; KEEP_DB=0; SETUP_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES=1 ;;
    --keep-db) KEEP_DB=1 ;;
    --ci) export NO_COLOR=1; init_colors; YES=1; SETUP_ARGS+=(--ci) ;;
    -h|--help) usage; exit 0 ;;
    --) shift; SETUP_ARGS+=("$@"); break ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if ((!YES)); then
  read -r -p "Delete .venv, node_modules and artifacts/$( ((KEEP_DB)) && echo " (keeping app.db)") and reinstall? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || { log_info "cancelled"; exit 0; }
fi

log_step "Removing local environments"
DB_BACKUP=""
if ((KEEP_DB)) && [[ -f "$REPO_ROOT/artifacts/app.db" ]]; then
  DB_BACKUP="$(mktemp)"; cp "$REPO_ROOT/artifacts/app.db" "$DB_BACKUP"
fi
for t in "$BACKEND_DIR/.venv" "$FRONTEND_DIR/node_modules" "$E2E_DIR/node_modules"; do
  [[ -e "$t" ]] && { rm -rf "$t"; log_info "deleted ${t#"$REPO_ROOT/"}"; }
done
bash "$REPO_ROOT/scripts/clean.sh" --all >/dev/null
if [[ -n "$DB_BACKUP" ]]; then
  mkdir -p "$REPO_ROOT/artifacts"; mv "$DB_BACKUP" "$REPO_ROOT/artifacts/app.db"; log_info "kept artifacts/app.db"
fi

log_step "Reinstalling (scripts/setup.sh)"
exec bash "$REPO_ROOT/scripts/setup.sh" "${SETUP_ARGS[@]}"
