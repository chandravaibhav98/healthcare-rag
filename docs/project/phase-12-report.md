# Phase 12 Report: Documentation, Final Review and Submission

- **Date:** 2026-11-20 · **Plan ref:** `plan.md` §4 Phase 12 · Milestone M4 (complete)
- **Result:** **exit criterion met on Linux.** A fresh clone, then `scripts/setup.sh`,
  then `scripts/reproduce.sh` gives:
  - SC1;
  - both evaluation splits, **equal to their records to four decimals**;
  - SC4 contract fuzzing and the functional E2E suite;
  - the demo MP4 and a submission bundle (6.2 MB zip with `RESULTS.md`).

  The Windows run is for the owner (§3, item 2).
- **Fixed on the way:** `setup --skip-playwright`, which CI's `quality` job uses, has
  failed its own verify step since Phase 7 (§4). This needs the owner's check of the CI
  history.

## 1. Deliverables

| Deliverable | Where |
| --- | --- |
| README: purpose, disclaimer, results snapshot, architecture diagrams (Mermaid + text), quick start (local, Compose, kind), configuration table, script index, layout, status, licence | `README.md` |
| RUNBOOK (9 sections) | `RUNBOOK.md` |
| … deploy, upgrade, roll back the **application and the index separately**; expand/contract migrations; runtime config | §3 |
| … swapping in the real repository: `DocumentSource` (**implemented and tested**), adapters for gateway/S3/Blob/SharePoint, workload identity, snapshot-then-build, conversion, **ACL design with retrieval-time filtering**, gold set, threshold, 10-point sign-off | §4 |
| … retrieved text as data, not instructions | §5 |
| … operations: metrics, **7 alert rules** (each with a runbook entry), log queries, PHI-redaction check, retention, backups, routines | §6 |
| … scaling path FlatIP → IVF/HNSW → external store, with recall and determinism conditions | §7 |
| Architecture (context, request sequence, modules, data, deployment, quality attributes) | `docs/Architecture.md` |
| API reference with **real** captured requests and responses | `docs/API.md` |
| ADRs finalised: 0006, 0007, 0008 accepted; 0001, 0002 await mentor sign-off (owner recommends accepting) | `docs/adr/` |
| Evaluation report: final, re-run in Phase 12, reproduction section | `docs/evaluation-report.md` |
| Technical summary for stakeholders (problem, approach, results against criteria, risks, decisions needed, next steps) | `docs/technical-summary.md` |
| Submission bundle: determinism manifest, dev + test reports with the low-confidence lists, contract JUnit, Playwright HTML report, demo MP4 + GIF + chapters, licence, notices, `RESULTS.md`, zip + SHA256SUMS | `scripts/reproduce.{sh,ps1}` → `artifacts/submission/` |
| Tagged release (images, prod manifests, SBOMs, demo) | `release.yml` + `demo.yml` on `v*` (Phase 10/11) |
| Licence: MIT; third-party notices generated from the lockfiles (35 Python + 91 JavaScript runtime packages, 4 base images; no unknown licences) | `LICENSE`, `THIRD_PARTY_NOTICES.md`, `backend/scripts/third_party_notices.py --check` |
| Alert rules for Compose and the Prometheus Operator, promtool unit tests in CI | `deploy/compose/observability/alerts*.yml`, `deploy/k8s/components/service-monitor/prometheus-rule.yaml` |
| `clean` and `reset-env` (in the plan's script catalogue, missing until now) | `scripts/` |

## 2. Exit criterion: fresh-clone reproduction (Linux)

A clean `git clone` of the candidate commit (the owner's history, 0818845, plus this
phase), with no artifacts, caches or environments:

| Step | Result |
| --- | --- |
| `scripts/setup.sh --ci --skip-playwright` | ✅ lint (13 checks including the new e2e type check), **532 backend tests** (PostgreSQL via Testcontainers included), 45 frontend tests |
| `scripts/reproduce.sh --ci` | ✅ "Reproduced exactly: **yes**" |
| … SC1 | 3 builds byte-identical, `6ce73ffaf982` |
| … dev / test-v2 | P@5 0.602 / 0.417 · pass rate 0.926 / 0.807 · false validations 0 / 0.167: every metric equals `baseline.json` / `test-v2-results.json` |
| … SC4 contract | 52 passed, 3 skipped (no negative inputs exist for the three probes) |
| … functional E2E | 20/20 |
| … demo | MP4 h264 1920×1080, 11 chapters |
| … bundle | `healthcare-rag-submission-<commit>.zip`, 6.2 MB, SHA-256 recorded |
| `scripts/reproduce.ps1 --quick --ci` (pwsh 7) | ✅ reproduced exactly |
| `scripts/reset-env.sh` / `.ps1 --keep-db` | ✅ environments rebuilt from the lockfiles; database kept |
| `--help` of all 28 script pairs (bash and PowerShell) | ✅ |

## 3. Final review checklist

| # | Check | Result |
| --- | --- | --- |
| 1 | Fresh clone on Linux | ✅ §2 |
| 2 | Fresh clone on **Windows** (Git Bash and PowerShell) | ⏳ **Owner.** Commands in the final message; CI's `windows-2025` jobs cover setup, lint, unit tests and SC1 parity on every PR |
| 3 | All scripts working | ✅ 28 `.sh` + `.ps1` pairs answer `--help`. Every script is exercised by CI, a phase verification or §2. The plan's `e2e` and `format` rows map to `test --e2e` and `lint --fix` (plan §5 updated) |
| 4 | No secrets in history | ✅ `gitleaks git` over **all 16 commits of the owner's repository** (from a `git bundle` of it): no leaks. No `.env`, key or credential file was ever committed. detect-secrets runs as a pre-commit hook and in CI |
| 5 | Licence | ✅ MIT (owner's choice) at Phase 12. **Superseded 2026-11-24:** the MIT licence was removed for handoff; the licence is the client's choice (README) |
| 6 | Third-party notices | ✅ Generated. All runtime dependencies are permissive (MIT, BSD, ISC, Apache-2.0, PSF, 0BSD). The only copyleft component is BusyBox (GPL-2.0) in the `rag-index` base image, with a source pointer |
| 7 | Docs build and links | ✅ Every relative link in README, RUNBOOK, CONTRIBUTING, plan and `docs/` resolves; the alert test checks that each alert's RUNBOOK entry exists |
| 8 | Alert rules | ✅ `promtool check rules` + 2 unit-test groups (healthy traffic stays quiet; each failure fires with the expected annotations); Compose config validated |
| 9 | Determinism unaffected by the `DocumentSource` refactor | ✅ `index_version` still `6ce73ffaf982` |

## 4. Defects found

| Defect | Impact | Fix |
| --- | --- | --- |
| `scripts/setup.* --skip-playwright` skipped `npm ci --prefix e2e`, but its verify step ran `test --all`, which fails with "e2e/node_modules is missing". The CI `quality` job runs exactly that command on Linux and Windows | Since Phase 7 (64bf448), `quality` must have failed in CI, and therefore `ci-passed` too. It was never visible here, because CI results have not been shared (OI-31) | e2e dependencies are always installed (lint now type-checks them too). With `--skip-playwright`, verify runs `--backend --frontend`; the E2E suite has its own CI job. Verified from a fresh clone |
| The Phase 11 commit (0818845) contains only `scripts/demo-record.sh`; the other 17 Phase 11 files were never committed | `main` has a demo script whose spec and helpers are missing | The commit commands in the final message add them first, as their own commit |
| The ServiceMonitor job label in Kubernetes is the Service name (`api`), so `up{job="rag-api"}` would never match | `RagApiDown` silent in Kubernetes | ServiceMonitor relabels `job` to `rag-api`, matching Compose |
| Plan §5 promised `clean` and `reset-env`, which did not exist | Catalogue drift | Both added (bash + PowerShell) and tested |

## 5. Open items at submission

| # | Item | Owner |
| --- | --- | --- |
| Decision | SC2 reading (literal vs ceiling-normalised P@5); ADR-0001 / 0002 sign-off | Mentor (technical summary §5) |
| OI-31 | First green CI run on GitHub, now including the §4 fix; then `scripts/github-protect.sh` (OI-39) | Owner |
| OI-21/22/27 | False-validation and paraphrase fixes need a new test-v3 | Next iteration |
| OI-42 | Document-level ACL filtering (designed in RUNBOOK §4.6), required before restricted documents | Real-repository pilot |
| Windows | Fresh-clone run on Windows (§3 item 2) | Owner |
