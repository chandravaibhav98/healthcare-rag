import { http, HttpResponse } from 'msw';

import * as f from './fixtures';

/** Default happy-path API. Tests override single routes with `server.use(...)`. */
export const handlers = [
  http.get('*/version', () => HttpResponse.json(f.version)),
  http.post('*/api/v1/auth/refresh', () =>
    HttpResponse.json({ title: 'Unauthorized', status: 401 }, { status: 401 }),
  ),
  http.post('*/api/v1/auth/login', async ({ request }) => {
    const body = (await request.json()) as { email: string };
    const role = body.email.split('@')[0];
    if (role === 'admin' || role === 'reviewer' || role === 'user') {
      return HttpResponse.json(f.tokens(role));
    }
    return HttpResponse.json(
      { title: 'Unauthorized', status: 401, detail: 'Invalid email or password.' },
      { status: 401 },
    );
  }),
  http.post('*/api/v1/auth/logout', () => new HttpResponse(null, { status: 204 })),
  http.post('*/api/v1/qa', async ({ request }) => {
    const body = (await request.json()) as { question: string };
    return HttpResponse.json(/yellow fever/i.test(body.question) ? f.qaAbstained : f.qaValidated);
  }),
  http.post('*/api/v1/escalations', async ({ request }) => {
    const body = (await request.json()) as { request_id: string };
    return HttpResponse.json(
      { request_id: body.request_id, status: 'queued', escalated_at: f.NOW },
      { status: 202 },
    );
  }),
  http.get('*/api/v1/admin/stats', () => HttpResponse.json(f.stats)),
  http.get('*/api/v1/admin/queries', () => HttpResponse.json(f.queryPage)),
  http.get('*/api/v1/admin/queries/:id', () => HttpResponse.json(f.queryDetail)),
  http.get('*/api/v1/admin/reviews', () => HttpResponse.json(f.reviewPage)),
  http.post('*/api/v1/admin/reviews/:id', async ({ request, params }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json(
      {
        id: '44444444-4444-4444-4444-444444444444',
        query_id: params.id,
        reviewer_id: null,
        note: '',
        corrected_citations: [],
        promote_to_gold: false,
        ...body,
        created_at: f.NOW,
        updated_at: f.NOW,
      },
      { status: 201 },
    );
  }),
  http.get('*/api/v1/admin/eval-runs', () =>
    HttpResponse.json({ items: [f.evalRun], total: 1, limit: 50, offset: 0 }),
  ),
  http.get('*/api/v1/admin/eval-runs/:id', () => HttpResponse.json(f.evalRun)),
  http.post('*/api/v1/admin/eval-runs', () =>
    HttpResponse.json(
      { ...f.evalRun, id: 'new-run', status: 'queued', scorecard: null },
      { status: 202 },
    ),
  ),
  http.get('*/api/v1/admin/index/versions', () => HttpResponse.json(f.indexVersions)),
  http.post('*/api/v1/admin/index/versions/:v/activate', ({ params }) =>
    HttpResponse.json({ ...f.indexVersions.items[1], version: params.v, is_active: true }),
  ),
  http.get('*/api/v1/admin/index/rebuild', () => HttpResponse.json(f.rebuildStatus)),
  http.post('*/api/v1/admin/index/rebuild', () =>
    HttpResponse.json({ ...f.rebuildStatus, running: true }, { status: 202 }),
  ),
  http.get('*/api/v1/admin/documents', () => HttpResponse.json(f.documents)),
  http.get('*/api/v1/admin/config', () => HttpResponse.json(f.config)),
  http.put('*/api/v1/admin/config', async ({ request }) => {
    const body = (await request.json()) as { values: unknown; comment: string };
    return HttpResponse.json({
      ...f.config,
      version: 1,
      values: body.values,
      comment: body.comment,
    });
  }),
  http.get('*/api/v1/admin/audit-log', () => HttpResponse.json(f.audit)),
];
