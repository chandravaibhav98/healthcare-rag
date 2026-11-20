# ADR-0013 — Quality gates, test tooling and supply-chain pinning

- **Status:** Accepted (Phase 7)
- **Date:** 2026-11-15
- **Plan ref:** `plan.md` §4 Phase 7, §6 · **Risks:** R3, R6, R10

## Context

Phases 0–6 wrote tests inside each phase. Phase 7 turns the test pyramid into gates that
fail the build, and adds the layers that were missing: contract fuzzing, browser E2E, a
load test and security scanning. Two constraints shape the choices: every gate must be
runnable on a developer's machine through `scripts/` (bash and PowerShell), and the
pipeline must not widen the supply-chain attack surface. The March 2026 Trivy compromise
(CVE-2026-33634: 76 of 77 `trivy-action` tags force-pushed to a credential stealer, and a
poisoned Trivy 0.69.4) happened to exactly the kind of security tooling this phase adds.

## Decision

| Concern | Choice | Why / alternative |
| --- | --- | --- |
| Coverage gate | `pytest-cov` JSON + `backend/scripts/coverage_gate.py` (lines + branches per prefix: `app/rag` 90, `app/services` 85, all 80); Vitest `coverage.thresholds` 70 | `--cov-fail-under` only checks one total; the plan sets per-layer targets |
| Contract fuzzing | Schemathesis via its **Python API** in parametrized pytest tests (one test per operation × positive/negative), against the committed `openapi.json` and the ASGI app | The pytest plugin fails on pytest 9 (OI-36). Using the committed snapshot means the fuzzed contract is the published one |
| Evaluation regression | `tests/regression/`: dev-pool non-regression vs `baseline.json`, SC3 on both splits, SC2 as P@5 / ceiling ≥ 0.70, held-out split pinned to its frozen record (false validations may not grow) | Quality regressions fail `scripts/test.sh` locally, not only in the CI eval job. The held-out split is observed, never tuned on |
| E2E | Playwright, Chromium only, one worker, `data-testid` selectors, its own disposable stack (`e2e_server.py` + `vite preview` of the production build) | Cross-browser runs add little to an internal tool; one worker because specs share a seeded DB |
| Accessibility | axe-core on every route in light and dark mode inside the E2E job (`a11y.spec.ts`); Lighthouse stays in the manual audit | Closes OI-29. Lighthouse needs a long-lived Chrome and is slow; axe catches the same WCAG failures |
| Load | k6 (`e2e/load/qa.js`), thresholds in the script so k6's exit code is the gate; PRs run 1 min, `main` runs the full 5 min | Small scripts, native thresholds; Locust needs a Python harness for the same result |
| Security | pip-audit (locked venv), npm audit (high+), bandit (medium+; low findings are reviewed asserts and subprocess calls already gated by ruff `S`), gitleaks (history), trivy fs (lockfiles + IaC, high+) | Each tool owns one surface; gitleaks has a single allowlisted path (`.secrets.baseline`, hashes only) |
| Supply chain | Third-party actions pinned to a **full commit SHA** (version in a comment); gitleaks and trivy downloaded as release binaries and checked against a SHA-256 recorded in the workflow; no `trivy-action`/`setup-trivy` | A tag can be force-pushed; a SHA cannot. Trivy 0.76.2 is a release after the compromised 0.69.4–0.69.6 range. GitHub's own actions follow in Phase 10 (OI-34) |

## Consequences

- Every gate has a local entry point: `scripts/test.* --all --coverage`,
  `scripts/load-test.*`, `scripts/security-scan.*`. CI calls the same scripts.
- The gates found real bugs on their first run (Phase 7 report §2), which is the evidence
  that they test behaviour rather than restate it.
- The E2E and load jobs add about 5 and 3–8 minutes of CI time. The 5-minute load run is
  limited to `main` and manual runs.
- Updating a scanner means updating its version and its SHA-256 together.
