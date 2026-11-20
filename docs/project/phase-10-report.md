# Phase 10 Report: CI/CD Pipeline

- **Date:** 2026-11-20 · **Plan ref:** `plan.md` §4 Phase 10 · Milestone M3 (part 3)
- **Result:** every deliverable is built and checked locally.
  - `ci.yml` now builds the images once and tests that build. It ends in a single
    required check, `ci-passed`.
  - `release.yml` publishes the tested images to GHCR, with SBOMs and optional
    signatures, and turns a `v*` tag into a GitHub Release with the prod manifests
    pinned by digest.
  - The rulesets that make `ci-passed` mandatory are JSON in git, applied by a script.
- **Exit criterion:** met by design and simulated locally. Enforcement depends on the
  repository's plan: rulesets need a public repository, or GitHub Pro or higher for a
  private one (OI-39). The first GitHub run confirms it (OI-31).
- **Decisions:** ADR-0016.

## 1. Deliverables

| Deliverable | Where |
| --- | --- |
| `ci.yml` rewritten. `changes` (docs-only detection) → every gate → `build` (Buildx bake, GHA cache, once) → `images` and `kubernetes` load that build → `ci-passed` aggregator. uv and npm caching and the Linux + Windows matrix (quality, determinism) are kept. Main runs are never cancelled. A `merge_group` trigger is ready for a merge queue | `.github/workflows/ci.yml` |
| Bake file for the three images (CI and local) | `deploy/docker/docker-bake.hcl` |
| Evaluation report, Playwright HTML reports (functional, Compose, kind), coverage, k6 summary, determinism manifests uploaded as artifacts | `ci.yml` (unchanged names) |
| `release.yml`, `publish` job: after a green main run, push that run's images (`sha-<commit>`, `main`, `rag-index:<index_version>`), Syft SBOMs, optional Cosign keyless signatures + SBOM attestations, `release-manifest.json` | `.github/workflows/release.yml`, `scripts/ci/publish-images.sh` |
| `release.yml`, `release` job: on `v*`, promote `sha-<commit>` → `vX.Y.Z` (digest unchanged), render the prod overlay pinned by digest, GitHub Release with manifest, SBOMs and notes | `scripts/ci/release.sh` |
| GHCR cleanup (untagged versions only) | `release.yml` `cleanup` |
| Branch protection as code: default branch (PR, linear history, `ci-passed` from GitHub Actions, up to date) and immutable `v*` tags | `.github/rulesets/*.json`, `scripts/github-protect.{sh,ps1}` |
| Every action pinned to a commit SHA (closes OI-34); Syft and Cosign checksum-verified | both workflows |
| Dependabot: actions, uv, npm (frontend + e2e), Docker, Compose; grouped, weekly, 7-day cooldown | `.github/dependabot.yml` |
| Docs | ADR-0016, `docs/releasing.md`, `scripts/ci/README.md`, README, CONTRIBUTING, `deploy/README.md`, `plan.md` |

`scripts/ci/*.sh` are bash only: they run on Linux runners and are never a developer
entry point, which is the documented exception to the `.sh` + `.ps1` rule.
`github-protect` is a developer script and has both.

## 2. Verification

GitHub Actions cannot run in the sandbox, so each part was checked separately with the
same commands.

| Check | Result |
| --- | --- |
| `actionlint` (with shellcheck on every `run:` block) on both workflows | Clean |
| `shellcheck -S warning` on `scripts/ci/*.sh`, `github-protect.sh`; pre-commit (all hooks CI runs) | Clean |
| No action left on a tag | 0 unpinned `uses:` |
| `docker buildx bake -f deploy/docker/docker-bake.hcl --load`; `--print` with `CACHE=gha` | Three images built; per-image `type=gha` cache entries rendered |
| `save-images.sh` → remove → `load-images.sh` | 200 MB artifact; `rag-api:local`, `rag-web:local`, `rag-index:build`, `rag-index:6ce73ffaf982` restored |
| `docker-up.sh --no-build --demo` on the **loaded** images (what the `images` job now does) | Stack healthy, seeded, 7/7 smoke checks through nginx |
| `ci-passed` logic, run on simulated `needs` | All success → pass. Docs-only with skips → pass. Skips on a code PR → **fail**. One failure → **fail**. One cancelled → **fail** |
| `changes` detection | docs/Markdown/rulesets → `false`; any code file → `true` |
| `publish-images.sh` against a local registry (distribution v3.1.0) | Pushed 3 images, 6 tags; digests recorded; 3 SPDX SBOMs |
| …with `SIGN=true` (Cosign key pair, offline flags) | `cosign verify` and `verify-attestation --type spdxjson` pass for all three digests |
| `release.sh v0.10.0-rc.1` | Promoted with unchanged digests; manifest has 4 image refs, all `@sha256:`; index version read from the published image; notes rendered |
| Rendered release manifest, `kubeconform -strict` | 21 resources, all valid |
| `release.sh` for a commit that was never published | Refused with a clear error, exit 1 |
| `github-protect.sh` and `.ps1` against a stubbed `gh` | Create, update by name, dry run; 403 on a private repository explains the plan limit, exit 1 |

## 3. Defects found while building

| Defect | Fix |
| --- | --- |
| The first render of the release manifest still contained `ghcr.io/OWNER/rag-api:CHANGE-ME`. The prod overlay already renames the images, so the release kustomization had to match the renamed names | Match `ghcr.io/OWNER/<image>`; the placeholder guard (`CHANGE-ME` or `OWNER/`) caught it and now stays in |
| `grep -Evq` reported "no code files" for a list that contained one, so a code PR would have skipped every gate | Use `grep -Ev … \|\| true` and test for output; the four cases above are the regression check |
| Cosign v3 fetches Sigstore's signing config even for key-pair signing, so it cannot sign offline by default | `COSIGN_ARGS` pass-through for offline tests; CI uses the default (keyless, online) |

## 4. Open issues

| # | Change |
| --- | --- |
| OI-34 | **Closed:** all actions are SHA-pinned and Dependabot updates them |
| OI-35 | Partly addressed: Dependabot now proposes base-image updates (Docker, Compose). Digest pinning is still open |
| OI-31 | Extended: the first GitHub run now confirms Phases 7–10, including the first real publish and release |
| OI-39 | **New:** rulesets on a private repository need GitHub Pro or higher. On Free, `ci-passed` reports but does not block. Owner decides: public repository or plan upgrade |
| OI-40 | **New:** Actions budget. About 3 billed hours per full run; a private repository on Free gets 2,000 minutes a month. Public: unlimited |

## 5. How this was verified

In a Linux sandbox with Docker, the repository at commit 2d6a6c4 plus the Phase 10
changes, actionlint, shellcheck, pwsh 7, kubeconform v0.8.0, Syft 1.57.2, Cosign 3.1.4,
and a local OCI registry (distribution 3.1.0) standing in for GHCR. The images are the
Phase 8 sandbox builds (OI-37).
