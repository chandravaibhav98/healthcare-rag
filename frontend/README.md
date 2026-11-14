# frontend

React + TypeScript SPA: the **Query Assistant** and the **Admin Dashboard**
([ADR-0012](../docs/adr/0012-frontend-architecture-and-accessibility.md)).

| Path                      | Purpose                                                                                                                      |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `src/api/`                | Generated OpenAPI types (`generated/`), typed client with refresh-on-401, in-memory session, Zod check of `/qa` answers      |
| `src/components/ui/`      | shadcn/ui-style primitives (Radix + Tailwind): button, badge, card, inputs, dialog/sheet, tooltip, table, status, pagination |
| `src/components/layout/`  | App shell: disclaimer banner, navigation, theme toggle, version footer                                                       |
| `src/features/assistant/` | Ask, answer card (status, confidence meter, citation chips), evidence panel, escalation, session history                     |
| `src/features/admin/`     | Overview, review queue, query explorer, evaluation, index & corpus, settings, audit log (lazy-loaded)                        |
| `src/features/auth/`      | Login, session restore, `RequireRole` guard                                                                                  |
| `src/test/`               | MSW handlers and fixtures, render helper, axe helper                                                                         |

```bash
npm ci
npm run dev            # http://localhost:5173 (proxies /api to the API on :8000)
npm test               # vitest + React Testing Library + MSW + axe
npm run gen:api        # regenerate API types after a contract change (or scripts/gen-client.sh)
npm run build          # type-check and production build to dist/
```

Use the root `scripts/` (`dev`, `lint`, `test`, `gen-client`) for everyday work. The
browser accessibility audit lives in [`../e2e/audit`](../e2e/audit/ui-audit.mjs).

Stable `data-testid` attributes mark every element the tests and the Phase 7/11
Playwright suites use; rename them only together with those suites.
