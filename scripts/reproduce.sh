#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# reproduce.sh: reproduce every reported metric and the demo from a fresh clone, then
# package the submission bundle (plan Phase 12 exit criterion). Parity: reproduce.ps1.
#
#   1. SC1  verify-determinism: 3 isolated index builds, byte-identical
#   2. SC2/SC3  evaluation on the dev pool and on the held-out test-v2 split; every
#      number must equal its record (backend/evaluation/baseline.json,
#      docs/evaluation/test-v2-results.json)
#   3. SC4  Schemathesis contract fuzzing of every API operation
#   4. Playwright functional E2E (HTML report)
#   5. the narrated demo video (scripts/demo-record)
#   6. bundle: artifacts/submission/<name>/ + <name>.zip + SHA256SUMS, with RESULTS.md
#
# Run scripts/setup.sh first. Re-running the held-out split here does not "spend" it:
# the configuration is frozen and the run only re-computes the recorded numbers.
# Exit code 1 if any number differs from its record or any gate fails. Criteria that are
# not met (SC2 as written; test-v2 false validations) are reported in RESULTS.md.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/reproduce.sh [--quick] [--skip-e2e] [--skip-demo] [--ci] [-h|--help]

  --quick       Metrics only: determinism, evaluation, contract (about 3 minutes)
  --skip-e2e    Skip the Playwright functional suite
  --skip-demo   Skip the demo video (it needs ffmpeg with libx264)
  --ci          Plain output (no colours)

Full run: about 12 minutes. Output: artifacts/submission/.
USAGE
}

E2E=1; DEMO=1; CI_FLAG=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick) E2E=0; DEMO=0 ;;
    --skip-e2e) E2E=0 ;;
    --skip-demo) DEMO=0 ;;
    --ci) export NO_COLOR=1; init_colors; CI_FLAG=(--ci) ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

require_cmd uv "Run scripts/setup.sh first."
require_cmd git "Install Git."
VERSION="$(git -C "$REPO_ROOT" describe --tags --always --dirty 2>/dev/null || echo unknown)"
NAME="healthcare-rag-submission-$VERSION"
SUB="$REPO_ROOT/artifacts/submission"
OUT="$SUB/$NAME"
rm -rf "$OUT" "$SUB/$NAME.zip" "$SUB/SHA256SUMS"
mkdir -p "$OUT"
REPORTS="$BACKEND_DIR/evaluation/reports"

# --- 1. SC1 -------------------------------------------------------------------------------
log_step "SC1: deterministic index (3 isolated builds)"
run bash "$REPO_ROOT/scripts/verify-determinism.sh" --runs 3 --save-manifest "$OUT/determinism-manifest.json"

# --- 2. SC2 / SC3 -------------------------------------------------------------------------
latest_report() { find "$REPORTS" -maxdepth 1 -type d -name "*-eval-$1-*" | sort | tail -n 1; }
for split in dev test; do
  log_step "Evaluation: $split"
  run bash "$REPO_ROOT/scripts/eval.sh" --split "$split"
  dir="$(latest_report "$split")"
  [[ -n "$dir" ]] || die "no $split report under $REPORTS"
  mkdir -p "$OUT/evaluation"
  cp -R "$dir" "$OUT/evaluation/$split"
done

# --- 3. SC4 -------------------------------------------------------------------------------
log_step "SC4: contract fuzzing (Schemathesis)"
CONTRACT=passed
uv run --directory "$BACKEND_DIR" pytest tests/contract -q \
  --junitxml="$OUT/contract-junit.xml" || CONTRACT=failed
log_info "contract: $CONTRACT"

# --- 4. E2E -------------------------------------------------------------------------------
E2E_RESULT=skipped
if ((E2E)); then
  log_step "Functional E2E (Playwright)"
  E2E_RESULT=passed
  npm --prefix "$REPO_ROOT/e2e" test || E2E_RESULT=failed
  [[ -d "$REPO_ROOT/e2e/playwright-report" ]] && cp -R "$REPO_ROOT/e2e/playwright-report" "$OUT/playwright-report"
  log_info "e2e: $E2E_RESULT"
fi

# --- 5. demo ------------------------------------------------------------------------------
DEMO_RESULT=skipped
if ((DEMO)); then
  log_step "Demo video"
  DEMO_RESULT=passed
  bash "$REPO_ROOT/scripts/demo-record.sh" --gif "${CI_FLAG[@]}" || DEMO_RESULT=failed
  if [[ "$DEMO_RESULT" == passed ]]; then
    mkdir -p "$OUT/demo"
    mp4="$(find "$REPO_ROOT/artifacts/demo" -maxdepth 1 -name 'healthcare-rag-demo-*.mp4' | sort | tail -n 1)"
    base="${mp4%.mp4}"
    cp "$mp4" "$base.gif" "$base.chapters.txt" "$OUT/demo/"
  fi
fi

# --- 6. bundle ----------------------------------------------------------------------------
log_step "Comparing with the recorded results and packaging"
cp "$REPO_ROOT/LICENSE" "$REPO_ROOT/THIRD_PARTY_NOTICES.md" "$OUT/"
cp "$REPO_ROOT/docs/evaluation-report.md" "$REPO_ROOT/docs/technical-summary.md" "$OUT/"
git -C "$REPO_ROOT" rev-parse HEAD >"$OUT/COMMIT"
run uv run --directory "$BACKEND_DIR" python scripts/reproduce_report.py \
  --out "$OUT" \
  --dev "$OUT/evaluation/dev/summary.json" \
  --test "$OUT/evaluation/test/summary.json" \
  --determinism "$OUT/determinism-manifest.json" \
  --contract "$CONTRACT" --e2e "$E2E_RESULT" --demo "$DEMO_RESULT" \
  --zip "$NAME"

log_step "Done"
log_info "Results:  artifacts/submission/$NAME/RESULTS.md"
log_info "Bundle:   artifacts/submission/$NAME.zip (checksum in artifacts/submission/SHA256SUMS)"
