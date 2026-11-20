#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# github-protect.sh: apply the repository rulesets in .github/rulesets/ with the GitHub
# CLI, so "a PR cannot merge with a failing quality gate" is configuration in git, not
# a settings page someone clicked once. Parity: github-protect.ps1.
#
#   main.json          default branch: PR required, linear history, no force-push or
#                      deletion, and the `ci-passed` check (ci.yml) must pass on an
#                      up-to-date branch
#   release-tags.json  v* tags cannot be moved or deleted (releases stay immutable)
#
# Idempotent: a ruleset that exists (matched by name) is updated in place.
# Needs `gh auth login` with admin rights on the repository. Rulesets need a public
# repository, or GitHub Pro/Team/Enterprise for a private one (docs/releasing.md).
# -----------------------------------------------------------------------------
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"

usage() {
  cat <<'USAGE'
Usage: scripts/github-protect.sh [--repo OWNER/NAME] [--dry-run] [--ci] [-h|--help]

  --repo OWNER/NAME   Target repository (default: the current checkout's GitHub remote)
  --dry-run           Show what would be created or updated; change nothing
  --ci                Plain output (no colours)
USAGE
}

REPO=""; DRY=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) [[ $# -ge 2 ]] || die "--repo needs a value"; REPO="$2"; shift ;;
    --dry-run) DRY=1 ;;
    --ci) export NO_COLOR=1; init_colors ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

require_cmd gh "Install the GitHub CLI: https://cli.github.com, then run: gh auth login"
require_cmd python3 "Python 3 is needed to read the ruleset files"
[[ -n "$REPO" ]] || REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)" \
  || die "not a GitHub checkout; pass --repo OWNER/NAME"
RULES_DIR="$REPO_ROOT/.github/rulesets"

log_step "Repository $REPO"
info="$(gh api "repos/$REPO" --jq '[.visibility, .permissions.admin] | @tsv')" \
  || die "cannot read $REPO (check the name and gh auth status)"
visibility="${info%%$'\t'*}"; admin="${info##*$'\t'}"
log_info "visibility: $visibility · admin: $admin"
[[ "$admin" == true ]] || die "you need admin rights on $REPO to manage rulesets"

existing="$(gh api "repos/$REPO/rulesets?includes_parents=false" --paginate \
  --jq '.[] | [.id, .name] | @tsv')"

failed=0
for file in "$RULES_DIR"/*.json; do
  name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["name"])' "$file")"
  id="$(awk -F'\t' -v n="$name" '$2 == n { print $1 }' <<<"$existing")"
  if [[ -n "$id" ]]; then verb="update"; method=PUT; path="repos/$REPO/rulesets/$id"
  else verb="create"; method=POST; path="repos/$REPO/rulesets"; fi
  if ((DRY)); then log_info "would $verb: $name ($(basename "$file"))"; continue; fi
  if out="$(gh api --method "$method" "$path" --input "$file" 2>&1)"; then
    log_ok "${verb}d: $name"
  else
    failed=1
    log_error "could not $verb '$name': $(head -c 300 <<<"$out")"
    if [[ "$out" == *403* && "$visibility" == private ]]; then
      log_warn "rulesets on a private repository need GitHub Pro, Team or Enterprise."
      log_warn "Make the repository public, or upgrade the plan, then re-run (docs/releasing.md)."
    fi
  fi
done
((failed)) && exit 1

if ((!DRY)); then
  log_step "Active rulesets"
  gh api "repos/$REPO/rulesets" --jq '.[] | "    \(.name) [\(.target), \(.enforcement)]"'
  log_info "Required check: ci-passed (GitHub Actions). Test it with a PR that breaks a gate."
fi
