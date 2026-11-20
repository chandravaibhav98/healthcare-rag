# e2e

Browser and load tests. One npm package (`package.json`), installed by `scripts/setup.*`.

| Folder | Contents | Phase |
| --- | --- | --- |
| `tests/` | Playwright functional E2E + the axe-core accessibility gate | 7 ✅ |
| `load/` | k6 load test of `/qa` (`qa.js`) | 7 ✅ |
| `audit/` | `ui-audit.mjs`: the Phase 6 exit check (screens + axe + Lighthouse) | 6 ✅ |
| `demo/` | Recorded demo | 11 |

## Functional E2E (`tests/`)

```bash
scripts/test.sh --e2e                    # or: npm --prefix e2e test
CHROME_PATH=/path/to/chrome scripts/test.sh --e2e   # use an installed Chrome
E2E_BASE_URL=http://localhost:5173 npm --prefix e2e test   # against a running stack
# Compose (scripts/docker-up.sh --demo) and kind (scripts/k8s-up.sh): pass their seeded password
E2E_BASE_URL=http://localhost:8080 E2E_PASSWORD=<SEED_ADMIN_PASSWORD from deploy/compose/.env> npm --prefix e2e test
E2E_BASE_URL=http://localhost:8088 E2E_PASSWORD=<SEED_ADMIN_PASSWORD from deploy/k8s/overlays/local/secrets.env> npm --prefix e2e test
```

Without `E2E_BASE_URL`, Playwright starts its own stack: a disposable, seeded API on
:8100 (`backend/scripts/e2e_server.py`, data in `artifacts/e2e/`, wiped on every start) and
the production build of the SPA on :4180 (`vite preview`, proxying `/api`). Accounts:
`admin@`, `reviewer@`, `user@example.org`, password `e2e-password-123`.

| Spec | Journeys |
| --- | --- |
| `assistant.spec.ts` | ask → validated with citations; evidence panel highlights; ask → abstain → escalate; session history |
| `auth.spec.ts` | sign-in per role; user denied the dashboard; reviewer without admin sections; anonymous → sign-in; RBAC enforced by the API (401/403) |
| `admin.spec.ts` | reviewer approves from the review queue; settings change versioned and visible in the audit log; query explorer filter + detail drawer |
| `a11y.spec.ts` | axe-core (WCAG 2.0–2.2 A/AA + best practices) on every route, light and dark |

Selectors use `data-testid` only. Workers: 1 (the specs share one database). CI retries
once and keeps traces and videos of failures; `npm --prefix e2e run report` opens the
HTML report.

## Load test (`load/qa.js`)

```bash
scripts/load-test.sh                          # the gate: 50 VUs x 5 min, p95 < 300 ms, 0 % 5xx
scripts/load-test.sh --vus 10 --duration 30s  # quick run
scripts/load-test.sh --target http://localhost:8000   # a running API (raise RATE_LIMIT_QA)
```

Needs [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) (`winget install k6`)
or Docker. Questions come from the held-out gold split, so both the validated and the
abstention paths are loaded. The summary goes to `artifacts/load/summary.json`.

## Phase 6 audit (`audit/`)

Lighthouse is not part of CI (it needs a long-running Chrome); the axe part of this audit
runs in CI as `tests/a11y.spec.ts`. To run the full audit against a freshly seeded stack
(it changes data):

```bash
scripts/seed.sh --reset --demo
scripts/dev.sh                                  # API :8000 + web :5173
BASE_URL=http://localhost:5173 CHROME_PATH="/c/Program Files/Google/Chrome/Application/chrome.exe" npm --prefix e2e run audit
```

Results go to `e2e/audit/results/` (git-ignored). The committed Phase 6 snapshot is in
`docs/project/phase-6-ui/`.
