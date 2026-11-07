#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# build-index.sh: build the deterministic index from corpus/, then verify it.
# Defaults come from .env / Settings (CORPUS_DIR, INDEX_DIR). Parity: build-index.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/build-index.sh [--corpus DIR] [--out DIR] [--inspect] [-h|--help]

  --corpus DIR   Corpus root (default: CORPUS_DIR, i.e. corpus/)
  --out DIR      Output directory (default: INDEX_DIR, i.e. artifacts/index/)
  --inspect      Print chunk statistics after building
USAGE
}

ARGS=(); VERIFY_ARGS=(); INSPECT=0; OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --corpus) [[ $# -ge 2 ]] || die "--corpus needs a value"; ARGS+=(--corpus "$(abs_path "$2")"); VERIFY_ARGS+=(--corpus "$(abs_path "$2")"); shift ;;
    --out) [[ $# -ge 2 ]] || die "--out needs a value"; OUT="$(abs_path "$2")"; ARGS+=(--out "$OUT"); shift ;;
    --inspect) INSPECT=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
require_cmd uv "Run scripts/setup.sh first."
INDEX_ARGS=(); [[ -n "$OUT" ]] && INDEX_ARGS=(--index "$OUT")

log_step "Build index"
run uv run --directory "$BACKEND_DIR" python scripts/pipeline.py build "${ARGS[@]}"
log_step "Verify index"
run uv run --directory "$BACKEND_DIR" python scripts/pipeline.py verify "${INDEX_ARGS[@]}" "${VERIFY_ARGS[@]}"
if ((INSPECT)); then
  log_step "Inspect"
  run uv run --directory "$BACKEND_DIR" python scripts/pipeline.py inspect --stats "${INDEX_ARGS[@]}"
fi
