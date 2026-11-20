#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# demo-record.sh: record the narrated product demo (plan Phase 11) and convert it to
# an MP4 with chapter markers. Parity: demo-record.ps1.
#
# From a cold start, with no running services:
#   1. build the index from corpus/ into artifacts/demo/index (deterministic, SC1);
#   2. run the Playwright `demo` project (e2e/demo/demo.spec.ts). Playwright starts a
#      fresh, seeded API on that index, plus a second index version to activate, and the
#      production SPA build. The spec checks that the API serves the index from step 1;
#   3. convert the .webm to H.264 MP4 (-preset veryfast, chapters embedded), and write
#      the chapter list (and, with --gif, a GIF teaser).
#
# Output: artifacts/demo/healthcare-rag-demo-<timestamp>.mp4 (+ .chapters.txt, and
# artifacts/demo/demo-chapters.txt for the latest run).
#
# --target records against a running stack instead (Compose: http://localhost:8080). It
# must be seeded with --demo. The recording changes its data (a review, a settings
# version, an evaluation run), so use a disposable stack.
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/demo-record.sh [--target URL --password PW] [--slow-mo MS] [--gif]
                              [--keep-webm] [--crf N] [--ci] [-h|--help]

  --target URL     Record against a running, demo-seeded stack (default: start a fresh one)
  --password PW    Password of admin@example.org on --target (or E2E_PASSWORD)
  --slow-mo MS     Delay per browser action in ms (default 120)
  --gif            Also write a 12-second GIF teaser (960 px wide)
  --keep-webm      Keep Playwright's raw .webm and test output
  --crf N          H.264 quality, lower = better and larger (default 20)
  --ci             Plain output (no colours)

Needs: uv, npm (e2e installed by scripts/setup.sh), ffmpeg with libx264 on PATH.
USAGE
}

TARGET=""; PASSWORD="${E2E_PASSWORD:-}"; SLOW_MO=120; GIF=0; KEEP=0; CRF=20
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) [[ $# -ge 2 ]] || die "--target needs a value"; TARGET="${2%/}"; shift ;;
    --password) [[ $# -ge 2 ]] || die "--password needs a value"; PASSWORD="$2"; shift ;;
    --slow-mo) [[ $# -ge 2 ]] || die "--slow-mo needs a value"; SLOW_MO="$2"; shift ;;
    --gif) GIF=1 ;;
    --keep-webm) KEEP=1 ;;
    --crf) [[ $# -ge 2 ]] || die "--crf needs a value"; CRF="$2"; shift ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
[[ "$SLOW_MO" =~ ^[0-9]+$ ]] || die "--slow-mo must be a whole number of milliseconds"
[[ "$CRF" =~ ^[0-9]+$ && "$CRF" -le 51 ]] || die "--crf must be 0-51"
[[ -z "$TARGET" || -n "$PASSWORD" ]] || die "--target needs --password (or E2E_PASSWORD)"

E2E_DIR="$REPO_ROOT/e2e"
OUT_DIR="$REPO_ROOT/artifacts/demo"
RUN_DIR="$OUT_DIR/run"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
BASE="$OUT_DIR/healthcare-rag-demo-$STAMP"

# --- 1. prerequisites -------------------------------------------------------------------
log_step "Prerequisites"
require_cmd npm "Install Node (see .nvmrc), then run scripts/setup.sh"
require_cmd ffmpeg "Install ffmpeg (Windows: winget install Gyan.FFmpeg; macOS: brew install ffmpeg; Debian/Ubuntu: apt install ffmpeg)"
# Captured first: `ffmpeg | grep -q` fails under pipefail when grep stops reading early.
ENCODERS="$(ffmpeg -hide_banner -encoders 2>/dev/null || true)"
[[ "$ENCODERS" == *libx264* ]] || die "this ffmpeg has no libx264 (H.264) encoder"
[[ -d "$E2E_DIR/node_modules" ]] || die "e2e/node_modules is missing: run scripts/setup.sh (or npm ci --prefix e2e)"
[[ -n "$TARGET" ]] || require_cmd uv "Install uv: https://docs.astral.sh/uv/"
# Playwright records with its own ffmpeg build. `setup` installs it with Chromium; with
# CHROME_PATH (an installed Chrome) it may be missing. Idempotent and quick when present.
if ! npm --prefix "$E2E_DIR" exec -- playwright install ffmpeg >/dev/null 2>&1; then
  log_warn "could not run 'playwright install ffmpeg' (offline?); recording uses what is installed"
fi
log_ok "ffmpeg with H.264 and Playwright are available"

rm -rf "$RUN_DIR"
mkdir -p "$OUT_DIR"

# --- 2. the index (cold start) -----------------------------------------------------------
EXPECT_INDEX=""
if [[ -z "$TARGET" ]]; then
  log_step "Building the index from corpus/ (artifacts/demo/index)"
  rm -rf "$OUT_DIR/index"
  run bash "$REPO_ROOT/scripts/build-index.sh" --out "$OUT_DIR/index"
  EXPECT_INDEX="$(node -e 'console.log(JSON.parse(require("fs").readFileSync(process.argv[1], "utf8")).index_version)' "$OUT_DIR/index/manifest.json")"
  log_ok "index_version $EXPECT_INDEX"
fi

# --- 3. record ---------------------------------------------------------------------------
log_step "Recording (about 3.5 minutes; Playwright starts a fresh seeded stack first)"
(
  cd "$E2E_DIR"
  export DEMO_SLOW_MO="$SLOW_MO"
  if [[ -n "$TARGET" ]]; then
    export E2E_BASE_URL="$TARGET" E2E_PASSWORD="$PASSWORD"
  else
    export E2E_CANDIDATE_INDEX=1 INDEX_DIR="$OUT_DIR/index" DEMO_EXPECT_INDEX="$EXPECT_INDEX"
    unset E2E_BASE_URL E2E_PASSWORD
  fi
  run npm exec -- playwright test --project=demo --reporter=list --output="$RUN_DIR"
)

WEBM="$(find "$RUN_DIR" -name '*.webm' -type f -print -quit)"
CHAPTERS="$(find "$RUN_DIR" -name chapters.json -type f -print -quit)"
[[ -n "$WEBM" ]] || die "Playwright wrote no video under $RUN_DIR"
[[ -n "$CHAPTERS" ]] || die "the demo wrote no chapters.json under $RUN_DIR"
log_ok "raw video: $(du -h "$WEBM" | cut -f1)"

# --- 4. convert --------------------------------------------------------------------------
log_step "Converting to MP4 (H.264, -preset veryfast, CRF $CRF, chapters)"
TEASER_START="$(node "$E2E_DIR/demo/chapters.mjs" "$CHAPTERS" "$BASE")"
run ffmpeg -hide_banner -loglevel error -y -i "$WEBM" -i "$BASE.ffmeta" \
  -map 0:v:0 -map_metadata 1 -map_chapters 1 \
  -c:v libx264 -preset veryfast -crf "$CRF" -pix_fmt yuv420p -r 25 \
  -movflags +faststart -an "$BASE.mp4"
cp "$BASE.chapters.txt" "$OUT_DIR/demo-chapters.txt"
rm -f "$BASE.ffmeta"

if ((GIF)); then
  log_step "GIF teaser (12 s from chapter 2)"
  run ffmpeg -hide_banner -loglevel error -y -ss "$TEASER_START" -t 12 -i "$BASE.mp4" \
    -vf "fps=10,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer" \
    "$BASE.gif"
fi

# --- 5. check the result ----------------------------------------------------------------
log_step "Checking the MP4"
probe() { ffprobe -v error "$@" "$BASE.mp4"; }
CODEC="$(probe -select_streams v:0 -show_entries stream=codec_name -of csv=p=0)"
SIZE="$(probe -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0)"
DURATION="$(probe -show_entries format=duration -of csv=p=0)"
NCHAP="$(probe -show_chapters -of csv=p=0 | grep -c . || true)"
[[ "$CODEC" == h264 ]] || die "expected H.264, got $CODEC"
[[ "$SIZE" == 1920x1080 ]] || die "expected 1920x1080, got $SIZE"
[[ "$NCHAP" -ge 10 ]] || die "expected at least 10 chapters, got $NCHAP"
log_ok "h264 $SIZE · ${DURATION%.*} s · $NCHAP chapters · $(du -h "$BASE.mp4" | cut -f1)"

((KEEP)) || rm -rf "$RUN_DIR"

log_step "Done"
log_info "Video:     ${BASE#"$REPO_ROOT/"}.mp4"
log_info "Chapters:  ${BASE#"$REPO_ROOT/"}.chapters.txt (also artifacts/demo/demo-chapters.txt)"
((GIF)) && log_info "Teaser:    ${BASE#"$REPO_ROOT/"}.gif"
[[ -n "$EXPECT_INDEX" ]] && log_info "Index:     $EXPECT_INDEX"
exit 0
