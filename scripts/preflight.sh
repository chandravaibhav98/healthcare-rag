#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# preflight.sh — READ-ONLY environment check run before Phase 0.
#
# Why: Phase 0's exit criterion is "scripts/setup.* brings a clean machine to
# green". This script finds a missing or outdated toolchain, or repository
# hygiene that would break determinism (CRLF corpus files, risky paths), before
# any code exists. Phase 0's setup.sh will call this script first.
#
# It never installs or modifies anything. Exit codes: 0 = ready, 1 = blocking
# problems found, 2 = bad usage. Parity: scripts/preflight.ps1.
# -----------------------------------------------------------------------------
set -euo pipefail

STRICT=0
NO_COLOR="${NO_COLOR:-}"

usage() {
  cat <<'EOF'
Usage: scripts/preflight.sh [--strict] [--ci] [-h|--help]

Read-only check of the toolchain and repository hygiene needed for Phase 0.

Options:
  --strict   Treat tools needed only by later phases (docker, kubectl, kind,
             k6, ffmpeg, pwsh) as required instead of optional.
  --ci       Disable colours (also honoured: NO_COLOR=1).
  -h, --help Show this help and exit.

Exit codes: 0 ready · 1 blocking problems found · 2 invalid arguments
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict) STRICT=1 ;;
    --ci) NO_COLOR=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ -t 1 && -z "$NO_COLOR" ]]; then
  C_OK=$'\e[32m'; C_WARN=$'\e[33m'; C_FAIL=$'\e[31m'; C_DIM=$'\e[2m'; C_OFF=$'\e[0m'
else
  C_OK=""; C_WARN=""; C_FAIL=""; C_DIM=""; C_OFF=""
fi

FAILS=0
WARNS=0
ok()   { printf '  %s[ OK ]%s %s\n' "$C_OK" "$C_OFF" "$1"; }
warn() { printf '  %s[WARN]%s %s\n' "$C_WARN" "$C_OFF" "$1"; WARNS=$((WARNS + 1)); }
fail() { printf '  %s[FAIL]%s %s\n' "$C_FAIL" "$C_OFF" "$1"; FAILS=$((FAILS + 1)); }
hint() { printf '         %s↳ %s%s\n' "$C_DIM" "$1" "$C_OFF"; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# version_ge A B → true when A >= B (dotted numeric versions).
version_ge() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" == "$2" ]]; }

# extract_version "<text>" → first dotted number, e.g. "v26.1.0" → 26.1.0
extract_version() { grep -oE '[0-9]+(\.[0-9]+)+' <<<"$1" | head -n1 || true; }

# check_tool <label> <min-version> <required:1|0> <phase/purpose> <install hint> <cmd...>
check_tool() {
  local label="$1" min="$2" required="$3" purpose="$4" install="$5"
  shift 5
  local bin="$1" out ver
  if ! command -v "$bin" >/dev/null 2>&1; then
    if [[ "$required" == 1 || "$STRICT" == 1 ]]; then
      fail "$label not found (needed: $purpose)"
    else
      warn "$label not found (optional now; needed: $purpose)"
    fi
    hint "$install"
    return
  fi
  out="$("$@" 2>&1 | head -n 3 || true)"
  ver="$(extract_version "$out")"
  if [[ -z "$ver" ]]; then
    warn "$label found but version could not be parsed"
  elif version_ge "$ver" "$min"; then
    ok "$label $ver (>= $min)"
  elif [[ "$required" == 1 || "$STRICT" == 1 ]]; then
    fail "$label $ver is older than required $min ($purpose)"
    hint "$install"
  else
    warn "$label $ver is older than recommended $min ($purpose)"
    hint "$install"
  fi
}

echo "Healthcare RAG — pre-flight check"
echo "Repository: $REPO_ROOT"
echo

echo "Required for Phase 0"
check_tool "git"  "2.30"  1 "version control"            "https://git-scm.com/downloads"               git --version
check_tool "uv"   "0.5.0" 1 "Python envs + lockfile"     "https://docs.astral.sh/uv/getting-started/installation/" uv --version
check_tool "node" "26.0.0" 1 "frontend tooling (.nvmrc)" "fnm install  (reads .nvmrc; get fnm: https://github.com/Schniz/fnm)" node --version
check_tool "npm"  "10.0.0" 1 "frontend lockfile"         "Bundled with Node"                           npm --version

# Python 3.12 is pinned in .python-version; uv can provision it on demand.
if command -v uv >/dev/null 2>&1; then
  if py="$(uv python find 3.12 2>/dev/null)"; then
    ok "Python 3.12 available to uv ($py)"
  else
    warn "Python 3.12 not yet installed for uv (uv can fetch it on first use)"
    hint "uv python install 3.12"
  fi
fi

echo
echo "Needed by later phases"
check_tool "pwsh"    "7.4"    0 "PowerShell script parity (Phase 0+)" "https://aka.ms/powershell"            pwsh --version
check_tool "docker"  "24.0"   0 "containers (Phase 8)"               "https://docs.docker.com/get-docker/"  docker --version
check_tool "kubectl" "1.30"   0 "Kubernetes (Phase 9)"               "https://kubernetes.io/docs/tasks/tools/" kubectl version --client
check_tool "kind"    "0.24"   0 "local cluster (Phase 9)"            "https://kind.sigs.k8s.io/"            kind version
check_tool "k6"      "0.50"   0 "load testing (Phase 7)"             "https://grafana.com/docs/k6/latest/set-up/install-k6/" k6 version
check_tool "ffmpeg"  "4.4"    0 "demo video encoding (Phase 11)"     "https://ffmpeg.org/download.html"     ffmpeg -version

echo
echo "Repository hygiene"
if [[ -f "$REPO_ROOT/.gitattributes" ]] && grep -q 'eol=lf' "$REPO_ROOT/.gitattributes"; then
  ok ".gitattributes enforces LF (determinism, SC1)"
else
  fail ".gitattributes missing or does not enforce eol=lf"
fi

# Spaces / non-ASCII in the path break some tools (Docker contexts, kind mounts).
if LC_ALL=C grep -q '[^ -~]' <<<"$REPO_ROOT"; then
  warn "Repository path contains non-ASCII characters"
  hint "Move the repo to a short ASCII path, e.g. C:\\dev\\healthcare-rag or ~/dev/healthcare-rag"
elif [[ "$REPO_ROOT" == *" "* ]]; then
  warn "Repository path contains spaces"
  hint "Move the repo to a path without spaces"
else
  ok "Repository path is ASCII without spaces"
fi

case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*)
    if (( ${#REPO_ROOT} > 80 )); then
      warn "Repository path is ${#REPO_ROOT} chars; node_modules may exceed Windows MAX_PATH (260)"
      hint "Use a shorter path, and/or: git config --global core.longpaths true"
    fi ;;
esac

if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  ok "Git repository initialised (branch: $(git -C "$REPO_ROOT" symbolic-ref --short HEAD 2>/dev/null || echo detached))"
  if [[ "$(git -C "$REPO_ROOT" config --get core.autocrlf || true)" == "true" ]]; then
    warn "core.autocrlf=true (harmless here because .gitattributes overrides it)"
    hint "git config core.autocrlf false"
  fi
  crlf_files="$(git -C "$REPO_ROOT" ls-files --eol 2>/dev/null | awk '$1 == "i/crlf" {print $NF}' || true)"
  if [[ -n "$crlf_files" ]]; then
    fail "Files committed with CRLF line endings:"
    printf '         %s\n' $crlf_files
    hint "git add --renormalize . && git commit -m 'chore: normalise line endings'"
  else
    ok "No CRLF files in the index"
  fi
else
  warn "Not a Git repository yet"
  hint "git init -b main   (see docs/project/phase-0-readiness.md)"
fi

echo
if (( FAILS > 0 )); then
  printf '%sNOT READY%s: %d blocking issue(s), %d warning(s).\n' "$C_FAIL" "$C_OFF" "$FAILS" "$WARNS"
  exit 1
fi
printf '%sREADY%s (%d warning(s)).\n' "$C_OK" "$C_OFF" "$WARNS"
exit 0
