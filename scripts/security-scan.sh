#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# security-scan.sh: dependency, code and secret scanning. Parity: security-scan.ps1.
#
#   pip-audit   backend dependencies (the locked virtualenv) against PyPI/OSV advisories
#   npm audit   frontend + e2e dependencies, fails on high or critical
#   bandit      backend code, fails on medium or higher (low findings are the reviewed
#               type-narrowing asserts and subprocess calls ruff's "S" rules already gate)
#   gitleaks    secrets in the git history (falls back to the working tree outside git)
#   trivy fs    vulnerable lockfiles + IaC misconfiguration, fails on high or critical
#   trivy image (--images) rag-api, rag-web and rag-index images: no fixable CRITICAL
#
# gitleaks and trivy run from a local binary or, failing that, a pinned Docker image.
# Without either they are skipped with a warning; --strict turns a skip into a failure
# (CI passes --strict so no scanner can silently drop out).
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

# Pinned scanner images (Docker fallback). Trivy: never 0.69.4-0.69.6, the releases
# poisoned in the March 2026 supply-chain attack (CVE-2026-33634).
GITLEAKS_IMAGE="${GITLEAKS_IMAGE:-ghcr.io/gitleaks/gitleaks:v8.30.1}"
TRIVY_IMAGE="${TRIVY_IMAGE:-aquasec/trivy:0.76.2}"

usage() {
  cat <<'USAGE'
Usage: scripts/security-scan.sh [--images] [--strict] [--only NAME[,NAME]] [--ci] [-h|--help]

  --images       Also scan the rag-api, rag-web and rag-index images (Phase 8)
  --strict       Fail when gitleaks/trivy are unavailable instead of skipping them
  --only LIST    Run a subset: pip-audit,npm-audit,bandit,gitleaks,trivy
  --ci           Plain output (no colours)
USAGE
}

IMAGES=0; STRICT=0; ONLY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --images) IMAGES=1 ;;
    --strict) STRICT=1 ;;
    --only) [[ $# -ge 2 ]] || die "--only needs a value"; ONLY=",$2,"; shift ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
wanted() { [[ -z "$ONLY" || "$ONLY" == *",$1,"* ]]; }

have_docker() { command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; }
unavailable() {
  if ((STRICT)); then
    log_error "$1 is not installed and Docker is not running (--strict)"
    STEP_FAILURES+=("$1 (unavailable)")
  else
    log_warn "$1 skipped: install it or start Docker (CI runs it with --strict)"
  fi
}
# MSYS_NO_PATHCONV stops Git Bash rewriting the container paths below.
docker_run() { MSYS_NO_PATHCONV=1 docker run --rm -v "$REPO_ROOT:/repo" -w /repo "$@"; }

if wanted pip-audit; then
  require_cmd uv "Run scripts/setup.sh first."
  log_step "pip-audit (backend)"
  run_step "pip-audit" uv run --directory "$BACKEND_DIR" pip-audit --skip-editable --progress-spinner off
fi

if wanted npm-audit; then
  require_cmd npm "Run scripts/setup.sh first."
  log_step "npm audit (frontend, e2e)"
  run_step "npm audit frontend" npm --prefix "$FRONTEND_DIR" audit --audit-level=high
  run_step "npm audit e2e" npm --prefix "$E2E_DIR" audit --audit-level=high
fi

if wanted bandit; then
  log_step "bandit (backend code)"
  run_step "bandit" uv run --directory "$BACKEND_DIR" bandit -q -r app evaluation scripts --severity-level medium
fi

if wanted gitleaks; then
  log_step "gitleaks (secrets)"
  if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    GL_ARGS=(git --redact --no-banner .)
  else
    GL_ARGS=(dir --redact --no-banner .)
  fi
  if command -v gitleaks >/dev/null 2>&1; then
    run_step "gitleaks" bash -c 'cd "$1" && shift && gitleaks "$@"' _ "$REPO_ROOT" "${GL_ARGS[@]}"
  elif have_docker; then
    run_step "gitleaks (docker)" docker_run "$GITLEAKS_IMAGE" "${GL_ARGS[@]}"
  else
    unavailable gitleaks
  fi
fi

if wanted trivy; then
  log_step "trivy fs (lockfiles, IaC)"
  TRIVY_ARGS=(fs --scanners vuln,misconfig --severity HIGH,CRITICAL --exit-code 1
    --skip-dirs node_modules --skip-dirs .venv --skip-dirs artifacts --no-progress .)
  if command -v trivy >/dev/null 2>&1; then
    run_step "trivy fs" bash -c 'cd "$1" && shift && trivy "$@"' _ "$REPO_ROOT" "${TRIVY_ARGS[@]}"
  elif have_docker; then
    run_step "trivy fs (docker)" docker_run "$TRIVY_IMAGE" "${TRIVY_ARGS[@]}"
  else
    unavailable trivy
  fi
  if ((IMAGES)); then
    # Plan Phase 8 gate: no CRITICAL vulnerability that has a fix. HIGH findings are
    # printed for the report but do not fail the scan (base-image CVEs often have no fix).
    log_step "trivy image (rag-api, rag-web, rag-index)"
    for img in rag-api:local rag-web:local rag-index:build; do
      if ! docker image inspect "$img" >/dev/null 2>&1; then
        if ((STRICT)); then log_error "$img not built"; STEP_FAILURES+=("trivy image $img (missing)")
        else log_warn "$img not built (scripts/docker-up.sh builds it); skipped"; fi
        continue
      fi
      IMG_ARGS=(image --scanners vuln --ignore-unfixed --severity CRITICAL --exit-code 1 --no-progress "$img")
      if command -v trivy >/dev/null 2>&1; then
        run_step "trivy image $img" trivy "${IMG_ARGS[@]}"
      elif have_docker; then
        run_step "trivy image $img (docker)" docker run --rm -v /var/run/docker.sock:/var/run/docker.sock "$TRIVY_IMAGE" "${IMG_ARGS[@]}"
      else
        unavailable trivy
        break
      fi
    done
  fi
fi

finish_steps "Security scan"
