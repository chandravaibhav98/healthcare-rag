> Part of the [documentation index](../README.md#documentation). Synthetic corpus only; not for clinical use.

# End-to-end, demo and load tests

Everything in `e2e/`. Command-level detail is in the folder
[README](../e2e/README.md).

## 1. Functional E2E (`e2e/tests/`)

Playwright specs for the critical journeys:

- ask → validated; ask → abstain → escalate;
- evidence panel (highlighting, numeric check);
- sign-in per role, RBAC denial;
- review approve flow and promote to gold;
- config change appears in the audit log;
- axe accessibility gate on every route (`a11y.spec.ts`).

```bash
scripts/test.sh --e2e                         # starts a disposable seeded API + preview build
npm --prefix e2e run report                   # HTML report
```

Selectors use `data-testid` only. One worker (specs share one database). CI retries once
and keeps traces and videos of failures.

## 2. Demo video (`e2e/demo/`)

```bash
scripts/demo-record.sh             # cold start → artifacts/demo/healthcare-rag-demo-<UTC>.mp4
scripts/demo-record.sh --gif       # plus a GIF teaser
```

One test with ten chapters at 1920×1080, with captions, a visible pointer and a
spotlight. It asserts every outcome it shows, so a broken build fails rather than
recording a misleading video. Needs ffmpeg with libx264.

| Chapter | Shows |
| --- | --- |
| 1 | Assistant, synthetic-corpus disclaimer |
| 2 | PPE question → validated, confidence meter, citations |
| 3 | Evidence panel: shared words, numeric check |
| 4 | Cold-chain question → validated from several sources |
| 5 | Out-of-scope question → needs review, escalated |
| 6 | Admin sign-in, Overview KPIs |
| 7 | Review queue: approve, promote to gold |
| 8 | Evaluation: trend, threshold sweep, run |
| 9 | Index versions: activate, roll back |
| 10 | Settings change → audit log |

## 3. Load test (`e2e/load/qa.js`)

```bash
scripts/load-test.sh                          # 50 VUs × 5 min, p95 < 300 ms, 0 % 5xx
scripts/load-test.sh --vus 10 --duration 30s
```

Needs k6 (or Docker). Questions come from the held-out gold split, so both the validated
and the abstention paths are exercised. Summary: `artifacts/load/summary.json`.

## 4. UI audit (`e2e/audit/`)

Lighthouse + axe against a seeded stack (changes data). Not in CI. The committed
snapshot is in `docs/project/phase-6-ui/`.

## 5. Manual testing

The manual checklist per phase and per deployment target is [`test-plan.md`](../test-plan.md);
results and findings are in [`project/manual-test-log.md`](project/manual-test-log.md).
