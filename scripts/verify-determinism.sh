#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# verify-determinism.sh: SC1 check. Builds the index N times in separate processes,
# each with a different PYTHONHASHSEED, and requires byte-identical artifacts.
# CI runs this on Linux and Windows and then compares the two manifests.
# Parity: verify-determinism.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/verify-determinism.sh [--runs N] [--corpus DIR] [--save-manifest FILE] [-h|--help]

  --runs N               Number of independent builds to compare (default 2, minimum 2)
  --corpus DIR           Corpus root (default: CORPUS_DIR)
  --save-manifest FILE   Keep the manifest of the first run (for cross-OS comparison)
USAGE
}

ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --runs) [[ $# -ge 2 ]] || die "--runs needs a value"; ARGS+=(--runs "$2"); shift ;;
    --corpus) [[ $# -ge 2 ]] || die "--corpus needs a value"; ARGS+=(--corpus "$(abs_path "$2")"); shift ;;
    --save-manifest) [[ $# -ge 2 ]] || die "--save-manifest needs a value"; ARGS+=(--save-manifest "$(abs_path "$2")"); shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
require_cmd uv "Run scripts/setup.sh first."

log_step "Determinism check (SC1)"
run uv run --directory "$BACKEND_DIR" python scripts/pipeline.py determinism "${ARGS[@]}"
