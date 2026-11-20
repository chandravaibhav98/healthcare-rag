# ADR-0016: CI/CD that builds once, gates once, and promotes the tested bits

- **Status:** Accepted (Phase 10)
- **Date:** 2026-11-20
- **Plan ref:** `plan.md` §4 Phase 10 · **Builds on:** ADR-0013 (gates, pinning), ADR-0014 (images), ADR-0015 (Kubernetes)

## Context

Phases 7–9 left a pipeline with 13 jobs. Phase 10 has to turn it into a delivery
pipeline: images published to a registry, SBOMs, optional signatures, release manifests,
and a rule that **a PR cannot merge with a failing quality gate**. Three things in the
existing pipeline worked against that:

1. The `images` and `kubernetes` jobs each built all three images, so the bits deployed
   to kind were not the bits scanned in `images`, and a release would have been a third
   build of unknown provenance.
2. There was no single check to require. Requiring 14 job names in branch protection
   breaks silently: a renamed job, a new job never added, or a skipped job (GitHub treats
   a skipped required check as passing) all let a PR merge.
3. GitHub's own actions were pinned by tag (OI-34).

## Decision

| Concern | Choice | Why / alternative |
| --- | --- | --- |
| Building | One `build` job: `docker buildx bake` over `deploy/docker/docker-bake.hcl` (api, web, index in parallel), layer cache in the GitHub Actions cache (`type=gha`, one scope per image), images loaded and saved as a 1-day `images` artifact | The same Dockerfiles as `docker-up`; the bake file also works locally (`docker buildx bake -f deploy/docker/docker-bake.hcl --load`) |
| Testing the images | `images` (Compose, E2E, Trivy) and `kubernetes` (kind, E2E, rollouts) **load** that artifact and start with `--no-build` | What was scanned is what was deployed |
| Publishing | `release.yml` runs on `workflow_run` of a **successful** `ci` run for a **push to main** in this repository, downloads that run's `images` artifact and pushes it to GHCR. Tags: `rag-api`, `rag-web` → `sha-<commit>`, `main`; `rag-index` → `<index_version>`, `sha-<commit>` | Nothing is rebuilt after testing. Rejected: building in the release job (untested bits); pushing from `ci.yml` (PR runs would need write tokens) |
| Releases | A `v*` tag promotes the tag commit's `sha-<commit>` manifests to `vX.Y.Z` with `buildx imagetools create` (registry-side, digest unchanged; the script checks this), renders the prod overlay **pinned by digest**, and attaches it, the manifest, the SBOMs and notes to a GitHub Release. A commit that never passed CI on main cannot be released | Release = a label on tested bits. Digests, not tags, in the manifests |
| SBOM | Syft (SPDX JSON) for each image, at publish and at release | Release asset and build artifact; `cosign attest` when signing is on |
| Signing | Cosign, **opt-in** via repository variable `SIGN_IMAGES=true`: keyless (GitHub OIDC → Fulcio), signature plus SBOM attestation per digest | Keyless writes image names and digests to the public Rekor log, which a private repository may not want. Hence opt-in |
| The required check | One aggregator job, `ci-passed`, `needs:` every gate, `if: always()`; fails on any failure or cancellation, and on any skip unless the PR is docs-only | Adding a gate = adding it to `needs`. Settings never change |
| Docs-only PRs | A `changes` job (git diff) skips the heavy jobs when only Markdown, `docs/` or rulesets changed; `hygiene` and `ci-passed` still run | A docs PR costs minutes instead of a full run (about 3 billed hours), and the required check never stays pending |
| Enforcement | Repository rulesets as JSON in `.github/rulesets/`, applied by `scripts/github-protect.{sh,ps1}`. Default branch: PR required, linear history, no force-push or deletion, `ci-passed` (GitHub Actions app, id 15368) required on an up-to-date branch. `v*` tags: no update, no deletion | Protection is reviewable configuration in git, not a settings page. Binding the check to the Actions app stops another integration from posting a fake `ci-passed` |
| Supply chain | Every action pinned to a full SHA with the version in a comment; Syft, Cosign, kind, kubeconform, trivy, gitleaks downloaded with a recorded SHA-256; Dependabot (actions, uv, npm, Docker, Compose) with a 7-day cooldown on version updates; `permissions: contents: read` by default, write scopes only on the release jobs that need them | Closes OI-34. The cooldown keeps a poisoned release out of the queue for the days it typically takes to be found |
| Registry hygiene | After each publish, delete **untagged** GHCR versions beyond the newest 20 | Tagged images (every `sha-*`, every release) and signatures are never touched |
| Main runs | Not cancelled by a newer push (`cancel-in-progress` only for PRs) | A cancelled main run would never publish |

## Consequences

- **Positive:** one build per commit, test results that apply to the released bits, a
  release that is a pure metadata operation, a required check that cannot drift, and a
  rendered manifest that names exact digests.
- **Negative:** a 200 MB artifact per CI run (kept 1 day). The release depends on CI on
  main having finished; a tag pushed together with its commit waits up to 60 minutes.
- **Platform limits** (GitHub, 2026): rulesets on a **private** repository need GitHub
  Pro, Team or Enterprise; on GitHub Free they only apply to public repositories. A
  private repository on Free also has 2,000 Actions minutes and 500 MB of artifact and
  package storage per month (Windows minutes count double). See OI-39 and OI-40.

## Alternatives considered

- **Merge queue instead of strict up-to-date branches:** `ci.yml` already runs on
  `merge_group`, so the ruleset can switch to a merge queue when there is more than one
  contributor. Not needed for one.
- **SLSA provenance via `actions/attest-build-provenance`:** good, but attestations on
  private repositories need GitHub Enterprise; Cosign covers signing for every plan.
- **Helm chart release:** not needed; the Kustomize prod overlay rendered with digests
  is the release artifact (ADR-0015).
