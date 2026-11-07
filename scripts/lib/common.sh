#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# scripts/lib/common.sh: shared helpers for every bash script in scripts/.
# Source it; never execute it. PowerShell parity: scripts/lib/Common.psm1.
#
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
# -----------------------------------------------------------------------------
# shellcheck disable=SC2034  # variables are consumed by the sourcing script

if [[ -n "${_HCRAG_COMMON_LOADED:-}" ]]; then return 0; fi
_HCRAG_COMMON_LOADED=1

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"
STEP_FAILURES=()

# UTF-8 mode for every Python process we start. Under Git Bash (mintty), stdout is a
# pipe and Python would otherwise fall back to the legacy Windows code page (cp1252),
# crashing on "›", "—" or "°C" (docs/project/working-agreements.md).
export PYTHONUTF8=1

# Colours: off when not a TTY, under CI, or when NO_COLOR is set (no-color.org).
init_colors() {
  if [[ -t 1 && -z "${NO_COLOR:-}" && -z "${CI:-}" ]]; then
    C_BLUE=$'\e[34m'; C_GREEN=$'\e[32m'; C_YELLOW=$'\e[33m'; C_RED=$'\e[31m'
    C_BOLD=$'\e[1m'; C_DIM=$'\e[2m'; C_OFF=$'\e[0m'
  else
    C_BLUE=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BOLD=""; C_DIM=""; C_OFF=""
  fi
}
init_colors

log_step()  { printf '\n%s==>%s %s%s%s\n' "$C_BLUE" "$C_OFF" "$C_BOLD" "$*" "$C_OFF"; }
log_info()  { printf '    %s\n' "$*"; }
log_ok()    { printf '    %s✔%s %s\n' "$C_GREEN" "$C_OFF" "$*"; }
log_warn()  { printf '    %s!%s %s\n' "$C_YELLOW" "$C_OFF" "$*" >&2; }
log_error() { printf '    %s✘%s %s\n' "$C_RED" "$C_OFF" "$*" >&2; }
die()       { log_error "$*"; exit 1; }

# require_cmd <command> <install hint>
require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' is required but not installed. $2"
}

# run <cmd...>: echo the command, then run it (output stays visible for debugging).
run() {
  printf '    %s$ %s%s\n' "$C_DIM" "$*" "$C_OFF"
  "$@"
}

# run_step <label> <cmd...>: run and record failure instead of aborting, so a
# single invocation reports every failing check rather than only the first one.
run_step() {
  local label="$1"; shift
  if run "$@"; then
    log_ok "$label"
  else
    log_error "$label"
    STEP_FAILURES+=("$label")
  fi
}

# finish_steps <summary-name>: print a summary; exit 1 if any run_step failed.
finish_steps() {
  if ((${#STEP_FAILURES[@]})); then
    printf '\n%s%s FAILED%s (%d): %s\n' "$C_RED" "$1" "$C_OFF" "${#STEP_FAILURES[@]}" "${STEP_FAILURES[*]}" >&2
    exit 1
  fi
  printf '\n%s%s passed.%s\n' "$C_GREEN" "$1" "$C_OFF"
}

# abs_path <path>: absolute path (target need not exist). Needed because backend
# commands run with --directory backend, which would break repo-relative paths.
abs_path() {
  case "$1" in
    /*|[A-Za-z]:[\\/]*) printf '%s\n' "$1" ;;
    *) printf '%s/%s\n' "$PWD" "$1" ;;
  esac
}

# load_dotenv [file]: export KEY=VALUE pairs (comments and blanks ignored).
# Existing environment variables win, matching pydantic-settings precedence.
load_dotenv() {
  local file="${1:-$REPO_ROOT/.env}" line key value
  [[ -f "$file" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
    key="${line%%=*}"; value="${line#*=}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    [[ -n "${!key+x}" ]] || export "$key=$value"
  done <"$file"
}
