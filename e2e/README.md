# e2e

| Folder | Contents | Phase |
| --- | --- | --- |
| `audit/` | `ui-audit.mjs`: drives every screen against a running stack, then axe (light + dark) and Lighthouse. The Phase 6 exit check | 6 ✅ |
| `tests/` | Playwright functional E2E | 7 |
| `demo/` | Recorded demo | 11 |

Run the audit against a freshly seeded development stack (it changes data):

```bash
scripts/seed.sh --reset --demo
scripts/dev.sh                                  # API :8000 + web :5173
cd e2e/audit && npm ci
BASE_URL=http://localhost:5173 CHROME_PATH="/c/Program Files/Google/Chrome/Application/chrome.exe" npm run audit
```

Results (screenshots and `result.json`) go to `e2e/audit/results/` (git-ignored). The
committed snapshot of the Phase 6 run is in `docs/project/phase-6-ui/`.
