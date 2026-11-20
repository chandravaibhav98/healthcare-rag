# Releasing and branch protection

How code gets from a pull request to a published release (Phase 10, ADR-0016).

```text
PR ─► ci.yml (every gate) ─► ci-passed ─► squash-merge to main
                                              │
main ─► ci.yml again ─► success ─► release.yml publish
                                    push ghcr.io/<owner>/rag-*:sha-<commit>, :main,
                                    rag-index:<index_version>; SBOMs; (signatures)
                                              │
git tag vX.Y.Z <commit> ─► release.yml release
                           promote sha-<commit> → vX.Y.Z (same digests),
                           render prod overlay pinned by digest, GitHub Release
```

## 1. One-time repository setup

1. **Actions permissions** (Settings → Actions → General): keep "Read repository contents"
   as the default workflow token permission. The release jobs ask for `packages: write`
   and `contents: write` themselves.
2. **Branch and tag protection:** `scripts/github-protect.sh` (or `.ps1`) applies
   `.github/rulesets/main.json` and `release-tags.json` with the GitHub CLI. It is
   idempotent and needs admin rights. Use `--dry-run` to preview it.

   ```bash
   gh auth login
   scripts/github-protect.sh            # or: scripts/github-protect.sh --repo OWNER/NAME
   ```

   **Plan limits:** rulesets apply to **public** repositories on GitHub Free. A
   **private** repository needs GitHub Pro, Team or Enterprise. Otherwise the script
   stops with a 403 and says so. Until then, `ci-passed` still reports on every PR, but
   nothing blocks a merge (OI-39).
3. **GHCR packages:** the first publish creates `rag-api`, `rag-web` and `rag-index` as
   private packages linked to the repository. Make them public in the package settings if
   the cluster should pull without credentials. Otherwise give the cluster an image pull
   secret.
4. **Signing (optional):** set the repository variable `SIGN_IMAGES=true`. Cosign then
   signs each digest keyless through GitHub OIDC and attaches the SBOM as an attestation.
   The image names and digests then appear in the public Rekor transparency log, so leave
   signing off for a confidential project.

## 2. Every pull request

- `ci-passed` is the only required check. It lists every gate in `needs:`, so a new gate
  only has to be added there.
- Docs-only PRs (Markdown, `docs/`, rulesets) skip the heavy jobs, and `ci-passed` still
  reports.
- Dependabot opens grouped weekly PRs (actions, Python, npm, base images). Treat them
  like any other PR.

## 3. Publishing (automatic)

After CI passes on a push to `main`, `release.yml`'s `publish` job pushes the images that
CI built and tested. The `release-manifest` artifact on that run, and the job summary,
list the digests:

| Image | Tags |
| --- | --- |
| `ghcr.io/<owner>/rag-api` | `sha-<commit>`, `main` |
| `ghcr.io/<owner>/rag-web` | `sha-<commit>`, `main` |
| `ghcr.io/<owner>/rag-index` | `<index_version>`, `sha-<commit>` |

## 4. Cutting a release

```bash
git switch main && git pull
# wait until CI and "release / publish images" are green for this commit
git tag -a v1.0.0 -m "v1.0.0"
git push origin v1.0.0
```

The `release` job:

1. checks that `sha-<commit>` exists for all three images; it waits up to 60 minutes
   for the main run to publish, then fails. A commit that never passed CI on main
   cannot be released.
2. adds the `v1.0.0` tag to those manifests with `docker buildx imagetools create`. This
   happens in the registry, and the digests stay the same (the script checks).
3. renders `deploy/k8s/overlays/prod` with every image pinned by digest to
   `healthcare-rag-v1.0.0.yaml` (fails if a placeholder survives).
4. creates the GitHub Release with that manifest, `release-manifest.json`, the three
   SBOMs and notes (digests plus the evaluation baseline), followed by GitHub's generated
   changelog. Tags with a hyphen (`v1.1.0-rc.1`) become pre-releases.

`v*` tags cannot be moved or deleted (ruleset). To fix a release, cut a new version.

**Deploying it:** set the host name and secret store in the prod overlay first
(`deploy/README.md`), then `kubectl apply -f healthcare-rag-v1.0.0.yaml`, or point a
GitOps tool at the tag.

## 5. Running the release scripts locally

`scripts/ci/*.sh` can be run against any registry, for example a local
[distribution](https://github.com/distribution/distribution) on `localhost:5000`:

```bash
docker buildx bake -f deploy/docker/docker-bake.hcl --load
bash scripts/ci/save-images.sh artifacts/images
source artifacts/images/images.env
REGISTRY=localhost:5000/me GIT_SHA=$(git rev-parse HEAD) INDEX_VERSION=$INDEX_VERSION \
  bash scripts/ci/publish-images.sh
git tag v0.0.1-test && REGISTRY=localhost:5000/me bash scripts/ci/release.sh v0.0.1-test
```

These need `syft` (and `cosign` for `SIGN=true`) on `PATH`, plus `kubectl`.

## 6. Actions budget

A full CI run bills roughly 3 hours of runner time. That is an estimate: 13 Linux
jobs, plus 2 Windows jobs that count double, each rounded up to the minute. Public
repositories get unlimited minutes. A private repository on GitHub Free gets 2,000
minutes a month, which is about 10 to 12 full runs (OI-40). A docs-only PR costs a few
minutes.
