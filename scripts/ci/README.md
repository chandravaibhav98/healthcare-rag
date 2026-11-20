# scripts/ci

Helpers called only by `.github/workflows/` on Linux runners (ADR-0016), so they are bash
only; everything a developer runs lives one level up with a PowerShell twin. Each one can
also be run locally against a test registry (see `docs/releasing.md`).

| Script | Used by | Does |
| --- | --- | --- |
| `save-images.sh OUT` | ci `build` | Tags `rag-index:<index_version>`, saves the three bake-built images to `OUT/images.tar.gz` (+ `images.env`) |
| `load-images.sh DIR` | ci `images`, `kubernetes`; release `publish` | `docker load` of that tarball: later jobs test the exact bits that were built |
| `publish-images.sh` | release `publish` (main) | Pushes `sha-<commit>` (+ `main`, + `rag-index:<index_version>`), records digests, SBOMs (Syft), optional Cosign signatures |
| `release.sh TAG` | release `release` (tags `v*`) | Promotes the already-published `sha-<commit>` images to `TAG` without rebuilding, renders the prod overlay pinned to digests, SBOMs, release notes |
