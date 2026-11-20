#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# eval.sh: Phase 4 evaluation. Checks the gold files, builds the index if needed,
# then runs retrieval + validation + threshold curve and prints the SC scorecard.
# Parity: eval.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/eval.sh [--split dev|test] [--gate] [--update-baseline] [-h|--help]

  --split dev|test     Gold split (default dev). Run test ONCE per frozen configuration.
  --gate               Fail if dev metrics regress vs backend/evaluation/baseline.json
  --update-baseline    Record the current dev scorecard as the new baseline
  --require-targets    With --gate, also require SC2 (P@5 >= 0.65) and SC3 (>= 0.80)
USAGE
}

ARGS=(); SPLIT=dev
while [[ $# -gt 0 ]]; do
  case "$1" in
    --split) [[ $# -ge 2 ]] || die "--split needs a value"; SPLIT="$2"; shift ;;
    --gate|--update-baseline|--require-targets) ARGS+=("$1") ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
require_cmd uv "Run scripts/setup.sh first."
load_dotenv
INDEX="${INDEX_DIR:-artifacts/index}"; [[ "$INDEX" = /* ]] || INDEX="$REPO_ROOT/$INDEX"

if [[ ! -f "$INDEX/manifest.json" ]]; then
  log_step "Build index (none at $INDEX)"
  run uv run --directory "$BACKEND_DIR" python scripts/pipeline.py build
fi
log_step "Gold files are current"
run uv run --directory "$BACKEND_DIR" python -m evaluation.build_gold --check
log_step "Evaluate ($SPLIT)"
run uv run --directory "$BACKEND_DIR" python -m evaluation.run --split "$SPLIT" "${ARGS[@]}"
