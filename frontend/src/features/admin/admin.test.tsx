import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { beforeAll, describe, expect, it } from 'vitest';

import { expectNoSeriousA11yViolations } from '@/test/axe';
import { renderApp } from '@/test/render';
import { server } from '@/test/server';

describe('Admin dashboard', () => {
  // The dashboard is a lazily loaded chunk. Without warming it, the first test pays the cold
  // import inside findBy*'s 1 s budget and fails on slower machines (seen on Windows).
  beforeAll(async () => {
    await import('./pages');
  }, 30_000);

  it('overview shows KPIs, charts with text alternatives, topics and reasons', async () => {
    renderApp({ route: '/admin', role: 'reviewer' });
    expect(await screen.findByTestId('kpi-total')).toHaveTextContent('62');
    expect(screen.getByTestId('kpi-pass-rate')).toHaveTextContent('72.6%');
    expect(screen.getByTestId('kpi-p95')).toHaveTextContent('10 ms');
    expect(
      within(screen.getByTestId('chart-confidence')).getByRole('table', { hidden: true }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('top-topics')).toHaveTextContent('hand-hygiene');
    expect(screen.getByTestId('abstention-reasons')).toHaveTextContent(/weakly related/i);
    await expectNoSeriousA11yViolations();
  });

  it('review queue: side-by-side evidence and a saved verdict', async () => {
    let posted: unknown = null;
    server.use(
      http.post('*/api/v1/admin/reviews/:id', async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(
          {
            id: 'r',
            query_id: 'q',
            reviewer_id: null,
            verdict: 'correct',
            note: '',
            corrected_citations: [],
            promote_to_gold: true,
            created_at: '2026-11-14T08:00:00Z',
            updated_at: '2026-11-14T08:00:00Z',
          },
          { status: 201 },
        );
      }),
    );
    const { user } = renderApp({ route: '/admin/review', role: 'reviewer' });
    expect(await screen.findByTestId('review-question')).toHaveTextContent('Patient [ID]');
    expect(screen.getByTestId('candidate-answer')).toHaveTextContent('soap and water');
    expect(screen.getByTestId('review-evidence')).toHaveTextContent('who-hh-001::technique::0001');
    await expectNoSeriousA11yViolations();

    // "correct" is pre-selected for an abstention; it needs a chunk id.
    await user.click(screen.getByTestId('review-submit'));
    expect(await screen.findByText(/needs at least one chunk id/i)).toBeInTheDocument();

    await user.type(screen.getByTestId('extra-chunks'), 'cdc-x::y::0001');
    await user.type(screen.getByTestId('review-note'), 'Use the CDC chunk');
    await user.click(screen.getByTestId('promote-to-gold'));
    await user.click(screen.getByTestId('review-submit'));
    expect(await screen.findByTestId('review-saved')).toBeInTheDocument();
    expect(posted).toEqual({
      verdict: 'correct',
      note: 'Use the CDC chunk',
      corrected_citations: ['cdc-x::y::0001'],
      promote_to_gold: true,
    });
  });

  it('review queue: empty state', async () => {
    server.use(
      http.get('*/api/v1/admin/reviews', () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
    );
    renderApp({ route: '/admin/review', role: 'reviewer' });
    expect(await screen.findByTestId('empty-state')).toHaveTextContent(/nothing to review/i);
  });

  it('query explorer: filters reach the API and the detail drawer opens', async () => {
    const urls: URL[] = [];
    server.use(
      http.get('*/api/v1/admin/queries', ({ request }) => {
        urls.push(new URL(request.url));
        return undefined; // fall through to the default handler
      }),
    );
    const { user } = renderApp({ route: '/admin/queries', role: 'reviewer' });
    expect(await screen.findAllByTestId('query-row')).toHaveLength(2);
    await expectNoSeriousA11yViolations();

    await user.selectOptions(screen.getByTestId('filter-status'), 'needs_review');
    await user.type(screen.getByTestId('filter-min'), '0.2');
    await user.type(screen.getByTestId('filter-text'), 'needle');
    await user.click(screen.getByTestId('filter-apply'));
    await waitFor(() => {
      const last = urls.at(-1);
      expect(last?.searchParams.get('status')).toBe('needs_review');
      expect(last?.searchParams.get('min_confidence')).toBe('0.2');
      expect(last?.searchParams.get('q')).toBe('needle');
    });

    await user.click(screen.getByRole('button', { name: /needlestick/i }));
    const drawer = await screen.findByTestId('query-drawer');
    expect(drawer).toHaveTextContent('Withheld candidate answer');
    expect(drawer).toHaveTextContent('req-abstained-0002');
    await expectNoSeriousA11yViolations();
    await user.keyboard('{Escape}');
    await waitFor(() => {
      expect(screen.queryByTestId('query-drawer')).not.toBeInTheDocument();
    });
  });

  it('evaluation: trend, sweep, low-confidence list and a run button for admins', async () => {
    let started = false;
    server.use(
      http.post('*/api/v1/admin/eval-runs', () => {
        started = true;
        return HttpResponse.json({}, { status: 202 });
      }),
    );
    const { user } = renderApp({ route: '/admin/evaluation', role: 'admin' });
    expect(await screen.findByTestId('eval-runs-table')).toHaveTextContent('0.60');
    expect(await screen.findByTestId('chart-threshold-sweep')).toBeInTheDocument();
    expect(await screen.findByTestId('low-confidence-table')).toHaveTextContent(
      'When should gloves be changed?',
    );
    await expectNoSeriousA11yViolations();
    await user.click(screen.getByTestId('run-evaluation'));
    await waitFor(() => {
      expect(started).toBe(true);
    });
  });

  it('evaluation: reviewers cannot start runs', async () => {
    renderApp({ route: '/admin/evaluation', role: 'reviewer' });
    await screen.findByTestId('eval-runs-table');
    expect(screen.queryByTestId('run-evaluation')).not.toBeInTheDocument();
  });

  it('index: versions with hashes, confirm-before-activate, documents and rebuild', async () => {
    const { user } = renderApp({ route: '/admin/index', role: 'admin' });
    const rows = await screen.findAllByTestId('version-row');
    expect(rows[0]).toHaveTextContent('Active');
    expect(rows[0]).toHaveTextContent('a1b2c3d4e5f6'); // pragma: allowlist secret (fake hash)
    expect(await screen.findByTestId('documents-table')).toHaveTextContent('who-hh-001');
    await expectNoSeriousA11yViolations();

    await user.click(screen.getByRole('button', { name: 'Activate version 0123456789ab' })); // pragma: allowlist secret (fake hash)
    const dialog = await screen.findByTestId('activate-dialog');
    expect(dialog).toHaveTextContent(/verified first/i);
    await user.click(within(dialog).getByTestId('activate-confirm'));
    await waitFor(() => {
      expect(screen.queryByTestId('activate-dialog')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('rebuild-index')).toBeEnabled();
  });

  it('index: activation failure is shown in the dialog', async () => {
    server.use(
      http.post('*/api/v1/admin/index/versions/:v/activate', () =>
        HttpResponse.json(
          { title: 'Conflict', status: 409, detail: 'Index 0123456789ab failed verification' }, // pragma: allowlist secret (fake hash)
          { status: 409 },
        ),
      ),
    );
    const { user } = renderApp({ route: '/admin/index', role: 'admin' });
    await user.click(await screen.findByRole('button', { name: 'Activate version 0123456789ab' })); // pragma: allowlist secret (fake hash)
    await user.click(await screen.findByTestId('activate-confirm'));
    expect(await screen.findByTestId('error-alert')).toHaveTextContent(/failed verification/i);
  });

  it('settings: preview from the sweep, validation, audited save', async () => {
    let body: unknown = null;
    server.use(
      http.put('*/api/v1/admin/config', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          version: 1,
          values: (body as { values: unknown }).values,
          updated_at: '2026-11-14T08:00:00Z',
          updated_by: null,
          comment: 'tighten',
        });
      }),
    );
    const { user } = renderApp({ route: '/admin/settings', role: 'admin' });
    const threshold = await screen.findByTestId('cfg-threshold');
    await waitFor(() => {
      expect(threshold).toHaveValue(0.6);
    });
    expect(await screen.findByTestId('preview-pass-rate')).toHaveTextContent('50%');
    await expectNoSeriousA11yViolations();

    await user.clear(threshold);
    await user.type(threshold, '0.7');
    expect(screen.getByTestId('preview-pass-rate')).toHaveTextContent('40%');

    await user.clear(screen.getByTestId('cfg-coverage'));
    await user.type(screen.getByTestId('cfg-coverage'), '0.5');
    await user.click(screen.getByTestId('config-save'));
    expect(await screen.findByText(/must add up to 1/i)).toBeInTheDocument();

    await user.clear(screen.getByTestId('cfg-coverage'));
    await user.type(screen.getByTestId('cfg-coverage'), '0.2');
    await user.type(screen.getByTestId('cfg-comment'), 'tighten');
    await user.click(screen.getByTestId('config-save'));
    await waitFor(() => {
      expect(body).toEqual({
        expected_version: 0,
        values: {
          threshold: 0.7,
          retrieval_floor: 0.15,
          weights: { coverage: 0.2, query_support: 0.6, retrieval: 0.2 },
        },
        comment: 'tighten',
      });
    });
  });

  it('settings: a concurrent change is reported', async () => {
    server.use(
      http.put('*/api/v1/admin/config', () =>
        HttpResponse.json({ title: 'Conflict', status: 409, detail: 'changed' }, { status: 409 }),
      ),
    );
    const { user } = renderApp({ route: '/admin/settings', role: 'admin' });
    const threshold = await screen.findByTestId('cfg-threshold');
    await waitFor(() => {
      expect(threshold).toHaveValue(0.6);
    });
    await user.clear(threshold);
    await user.type(threshold, '0.65');
    await user.type(screen.getByTestId('cfg-comment'), 'try');
    await user.click(screen.getByTestId('config-save'));
    expect(await screen.findByTestId('error-alert')).toHaveTextContent(/someone else changed/i);
  });

  it('settings are read-only for reviewers', async () => {
    renderApp({ route: '/admin/settings', role: 'reviewer' });
    expect(await screen.findByTestId('cfg-threshold')).toBeDisabled();
    expect(screen.queryByTestId('config-save')).not.toBeInTheDocument();
  });

  it('audit log: filters by action', async () => {
    const urls: URL[] = [];
    server.use(
      http.get('*/api/v1/admin/audit-log', ({ request }) => {
        urls.push(new URL(request.url));
        return undefined;
      }),
    );
    const { user } = renderApp({ route: '/admin/audit', role: 'admin' });
    expect(await screen.findByTestId('audit-table')).toHaveTextContent('config.update');
    await expectNoSeriousA11yViolations();
    await user.type(screen.getByTestId('audit-action'), 'auth.');
    await user.click(screen.getByTestId('audit-apply'));
    await waitFor(() => {
      expect(urls.at(-1)?.searchParams.get('action')).toBe('auth.');
    });
  });
});
