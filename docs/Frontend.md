> Part of the [documentation index](../README.md#documentation). Synthetic corpus only; not for clinical use.

# Frontend

React + TypeScript single-page app in `frontend/` (ADR-0012). Folder
[README](../frontend/README.md) has component-level notes.

## 1. Structure

```text
src/
├── app/          router, providers, layout
├── api/          generated OpenAPI types + thin fetch wrapper (never edited by hand)
├── features/
│   ├── assistant/   QuestionForm, AnswerCard, EvidencePanel, EscalateButton, HistorySidebar
│   ├── admin/       Overview, ReviewQueue, QueryExplorer, Evaluation, Index, Settings, AuditLog
│   └── auth/        AuthProvider, LoginPage, RequireRole
├── components/   shared UI
├── hooks/ · lib/ · pages/ (status pages: 403, 404)
└── test/         Vitest setup, MSW handlers
```

## 2. Screens

| Route | Role | What it does |
| --- | --- | --- |
| `/` | anyone (if `ALLOW_ANONYMOUS_QA`) or `user` | Ask; status badge, confidence meter with signal breakdown, `[n]` citation chips, evidence panel with shared words highlighted and numbers checked; abstentions offer **Escalate for review** |
| `/login` | — | Sign in |
| `/admin` | reviewer, admin | Overview KPIs and trends |
| `/admin/review` | reviewer, admin | Review queue: approve, reject, correct, promote to the gold set |
| `/admin/queries` | reviewer, admin | Query explorer with filters and detail drawer |
| `/admin/evaluation` | reviewer, admin | Runs, P@5 / pass-rate trend, threshold sweep, analyst list, run an evaluation |
| `/admin/index` | reviewer, admin (the API enforces admin for writes) | Index versions, manifest hashes, activate / roll back |
| `/admin/settings` | reviewer, admin (the API enforces admin for writes) | Threshold and weights with an impact preview; changes are audited |
| `/admin/audit` | admin | Audit log |

Routes and their role guards are defined in `src/app/App.tsx`; the API's RBAC matrix is the authority for what each role may change ([API.md](API.md)).

## 3. Key decisions

- **Contract first.** `scripts/gen-client.sh` regenerates `src/api/` types from
  `backend/openapi.json`; `--check` fails CI on drift.
- **Server state** in TanStack Query; runtime response validation with Zod.
- **Auth.** Access token in memory; refresh token in an httpOnly, `SameSite=Strict`
  cookie scoped to `/api/v1/auth`. Route guards by role.
- **Same origin in deployment.** nginx (Compose) or the Gateway (Kubernetes) serves the
  SPA and proxies `/api`, so no CORS is needed. In dev, Vite runs on :5173 and the API on
  :8000. `VITE_API_BASE_URL` is empty unless the API lives on another origin.
- **Accessibility.** WCAG 2.2 AA; axe gate on every route in E2E; dark mode; responsive.
- **Selectors.** `data-testid` attributes for Playwright.

## 4. Commands

```bash
scripts/dev.sh --web-only            # Vite on :5173
npm --prefix frontend test           # Vitest + RTL + MSW
scripts/test.sh --frontend --coverage
scripts/lint.sh                      # eslint, prettier, tsc
```
