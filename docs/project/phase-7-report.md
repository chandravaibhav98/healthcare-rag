# Phase 7 Report — Test Hardening & Quality Gates

- **Date:** 2026-11-15 · **Plan ref:** `plan.md` §4 Phase 7, §6 · Milestone M2 (quality part)
- **Result:** every Phase 7 deliverable is built and every gate passes when run through
  the same scripts CI calls. The new gates found **eight real defects** on their first run
  (§2); all are fixed. **Exit criterion** ("CI is green with every gate enforced"): met
  locally and in a Linux sandbox; the first GitHub run confirms it (OI-31).
- **Decisions:** ADR-0013 (gate design, Schemathesis via its Python API, SHA-pinned
  third-party actions and checksum-verified scanners after the March 2026 Trivy
  supply-chain compromise).
- **Contract:** 1.3.1 (documentation precision from contract fuzzing; `/qa` unchanged).

## 1. Deliverables and results

| Gate | Tooling | Result | CI job |
| --- | --- | --- | --- |
| Backend coverage | pytest-cov + `scripts/coverage_gate.py` | `app/rag` **95.9 %** (≥ 90), `app/services` **95.6 %** (≥ 85), overall **93.2 %** (≥ 80), lines + branches | `quality` |
| Frontend coverage | Vitest v8 thresholds | lines **92.0 %**, statements 90.5 %, functions 89.9 %, branches 76.1 % (all ≥ 70) | `quality` |
| Backend tests | unit, property (Hypothesis), integration, API, contract | **481 passed, 44 skipped** in the sandbox (no Docker there, so the PostgreSQL variants skip, plus 3 empty negative-fuzz cases); the PostgreSQL variants pass against a local PostgreSQL 16 on the VM (Testcontainers in CI) | `quality` |
| Contract fuzzing | Schemathesis 4.30, every operation × positive/negative | **47 passed, 3 skipped** (no negative inputs exist for parameterless GETs) at 20 and at 150 examples per operation; CI runs 100 | `contract` |
| Evaluation regression | `tests/regression/` (11 tests) | dev pool at baseline; SC3 0.926 (dev) / 0.807 (held-out) ≥ 0.80; P@5 / ceiling 0.73 / 0.72 ≥ 0.70; held-out pinned to its frozen record | `quality` |
| Functional E2E | Playwright 1.65, Chromium | **20 tests** (12 functional journeys + 8 axe tests over 9 pages); **40/40** with `--repeat-each=2`; the 12 journeys 36/36 with `--repeat-each=3` | `e2e` |
| Accessibility | axe-core in `a11y.spec.ts` | 0 violations on every route, light and dark (after fix 8) | `e2e` |
| Load | k6 2.4, `e2e/load/qa.js` | **50 VUs × 5 min: 14,151 requests (47/s), p95 178.7 ms, p99 312 ms, 0 % 5xx, 100 % contract checks.** A forced threshold (`--p95 5`) exits non-zero, so the gate can fail | `load` |
| Security | pip-audit, npm audit, bandit, gitleaks, trivy fs | pip-audit: 0 known vulnerabilities · npm audit: 0 (frontend, e2e) · bandit: 0 medium/high (12 low, reviewed) · gitleaks: 0 leaks in history and tree · trivy fs misconfig: 0 (CVE database: OI-32) | `security` |
| Scripts | `test.*` `--backend --frontend --e2e --all --coverage`; `load-test.*`; `security-scan.*` | bash and PowerShell twins; PowerShell parse-checked and run on the VM | — |

Load-test environment: one uvicorn worker on a 2-vCPU Linux sandbox, SQLite query log.
The same profile on the Windows VM (Python stand-in for k6, because k6 cannot be
downloaded there) gave p95 39 ms over 4,464 requests.

## 2. Defects found by the new gates

| # | Found by | Defect | Fix |
| --- | --- | --- | --- |
| 1 | Schemathesis | The query-log writer's `asyncio.Queue` bound to the first event loop, so a second app lifespan (tests, reloads) could not log | Queue created in `start()`; `stop()` resets the writer |
| 2 | Schemathesis | List `sort` was a free string: schema-valid values got 422 | `sort` is an enum per list (`QuerySort`, `EvalRunSort`, `AuditSort`) |
| 3 | Schemathesis | A huge `offset` reached the database and returned **500** | `offset` ≤ 1,000,000 (422 beyond) |
| 4 | Schemathesis | `/admin/stats?to=0001-01-01` overflowed date arithmetic: **500** | 422 "'to' is out of range"; regression test added |
| 5 | Schemathesis | The document did not declare optional auth, malformed-JSON 400s, problem+json media types or the NDJSON export | All documented (contract 1.3.1) |
| 6 | Playwright | **Review saved silently without confirmation**: saving moves the queue to the next item, which unmounted the form that owned the mutation, so its success callback never ran | Mutation owned by the page |
| 7 | Playwright | **A reviewer's verdict could be overwritten**: the form reset itself from an effect when the detail query swapped from the previous item's placeholder data, racing user input | Form keyed by item id; defaults computed at mount, no reset effect |
| 8 | axe gate | Evidence text boxes in the review queue scrolled but were not keyboard-reachable (WCAG 2.1.1) | Focusable labelled regions with a focus ring |

`tsc` also caught one consequence of fix 2: the explorer's sort `<select>` now narrows to
the enum instead of passing any string.

## 3. Supply-chain posture

The Trivy ecosystem was compromised in March 2026 (CVE-2026-33634): 76 of 77
`aquasecurity/trivy-action` tags and all `setup-trivy` tags were force-pushed to a
credential stealer, and Trivy 0.69.4 was a malicious release. This phase adds security
tooling to CI, so it avoids that path entirely: no Trivy action; Trivy 0.76.2 and gitleaks
8.30.1 are downloaded as release binaries and checked against SHA-256 values recorded in
the workflow; the one third-party action (`grafana/setup-k6-action`) is pinned to a commit
SHA. Pinning GitHub's own actions is OI-34 (Phase 10).

## 4. Open issues

Closed: **OI-29** (the axe part of the browser audit now runs in CI as `a11y.spec.ts`;
Lighthouse stays a manual check, ADR-0013).

New: OI-31 (first GitHub run), OI-32 (Trivy CVE database unreachable in the sandbox),
OI-33 (image scan in Phase 8), OI-34 (SHA-pin GitHub's own actions), OI-35 (Docker
fallback images not pulled here), OI-36 (Schemathesis pytest plugin vs pytest 9).
OI-27 (near-domain false validation) is unchanged and is now visible as a gate: the
held-out false-validation rate is pinned at its recorded 0.167 and may only go down.

## 5. Verification log

- Backend: `scripts/test.sh --all --coverage --ci` in the Linux sandbox (481 passed,
  coverage gates met, 45 Vitest tests, 12 Playwright specs); the PostgreSQL variants
  (214 integration + API tests) against a local PostgreSQL 16 on the Windows VM.
- `scripts/lint.sh --ci`: ruff, `mypy --strict` (157 files), contract snapshots, eslint,
  prettier, tsc, API types current. pre-commit (all hooks) and `actionlint` clean.
- k6 5-minute run and the security scan with real k6 / gitleaks / trivy binaries in the
  sandbox; PowerShell scripts parse-checked, and `security-scan.ps1` run on the VM.

## 6. Hand-off to Phase 8

`e2e_server.py` and `E2E_BASE_URL` let the same Playwright suite and the k6 script run
against the Compose and kind stacks unchanged (`scripts/test.sh --e2e` with
`E2E_BASE_URL`, `scripts/load-test.sh --target`). `security-scan --images` is ready to
receive the Trivy image scan.
