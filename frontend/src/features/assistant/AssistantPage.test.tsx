import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { expectNoSeriousA11yViolations } from '@/test/axe';
import { renderApp } from '@/test/render';
import { server } from '@/test/server';

const QUESTION = 'How long should hand hygiene with alcohol-based handrub take?';

describe('Query Assistant', () => {
  it('shows a validated answer with status, confidence, citations and evidence', async () => {
    const { user } = renderApp();
    await user.type(screen.getByTestId('question-input'), QUESTION);
    await user.click(screen.getByTestId('ask-button'));

    const card = await screen.findByTestId('answer-card');
    expect(within(card).getByTestId('status-badge')).toHaveTextContent('Validated');
    expect(within(card).getByRole('meter', { name: /confidence/i })).toHaveAttribute(
      'aria-valuenow',
      '81',
    );
    expect(within(card).getByTestId('answer-text')).toHaveTextContent('20–30 seconds');

    // The first citation opens automatically; its shared words are highlighted.
    const panel = screen.getByTestId('evidence-panel');
    expect(
      within(panel).getByRole('heading', { name: /hand hygiene in health care/i }),
    ).toBeInTheDocument();
    const marks = within(screen.getByTestId('evidence-text')).getAllByText(
      (_, el) => el?.tagName === 'MARK',
    );
    expect(marks.map((m) => m.textContent)).toEqual(expect.arrayContaining(['handrub', 'seconds']));
    expect(within(panel).getByTestId('number-checks')).toHaveTextContent('20');

    // Clicking another source switches the panel and flags a superseded document.
    await user.click(screen.getByTestId('citation-item-2'));
    expect(
      within(screen.getByTestId('evidence-panel')).getByTestId('superseded-badge'),
    ).toBeInTheDocument();
    await expectNoSeriousA11yViolations();
  });

  it('submits with Enter and keeps Shift+Enter for new lines', async () => {
    const { user } = renderApp();
    const input = screen.getByTestId('question-input');
    await user.type(input, 'line one{Shift>}{Enter}{/Shift}line two');
    expect(input).toHaveValue('line one\nline two');
    await user.type(input, '{Enter}');
    expect(await screen.findByTestId('answer-card')).toBeInTheDocument();
  });

  it('validates the question length before calling the API', async () => {
    const { user } = renderApp();
    await user.type(screen.getByTestId('question-input'), 'hi{Enter}');
    expect(await screen.findByRole('alert')).toHaveTextContent(/at least 3 characters/i);
    expect(screen.queryByTestId('answer-card')).not.toBeInTheDocument();
  });

  it('explains an abstention, lists candidate sources and escalates for review', async () => {
    let escalated: unknown = null;
    server.use(
      http.post('*/api/v1/escalations', async ({ request }) => {
        escalated = await request.json();
        return HttpResponse.json(
          {
            request_id: 'req-abstained-0002',
            status: 'queued',
            escalated_at: '2026-11-14T08:00:00Z',
          },
          { status: 202 },
        );
      }),
    );
    const { user } = renderApp();
    await user.type(
      screen.getByTestId('question-input'),
      'What is the yellow fever vaccine dose?{Enter}',
    );
    const abstention = await screen.findByTestId('abstention');
    expect(abstention).toHaveTextContent(/no validated answer/i);
    expect(abstention).toHaveTextContent(/key terms/i);
    expect(screen.getByTestId('status-badge')).toHaveTextContent('Needs review');
    expect(screen.getByTestId('citation-list')).toHaveTextContent('Hand Hygiene in Health Care');

    await user.click(screen.getByTestId('escalate-button'));
    const dialog = await screen.findByTestId('escalate-dialog');
    await user.type(within(dialog).getByTestId('escalation-note'), 'Please check');
    await expectNoSeriousA11yViolations();
    await user.click(within(dialog).getByTestId('escalation-submit'));
    expect(await screen.findByTestId('escalation-done')).toHaveTextContent(
      /sent to the reviewers/i,
    );
    expect(escalated).toEqual({ request_id: 'req-abstained-0002', note: 'Please check' });
  });

  it('shows a clear message when escalation is unavailable', async () => {
    server.use(
      http.post('*/api/v1/escalations', () =>
        HttpResponse.json(
          { title: 'Service Unavailable', status: 503, detail: 'No database.' },
          { status: 503 },
        ),
      ),
    );
    const { user } = renderApp();
    await user.type(screen.getByTestId('question-input'), `${QUESTION}{Enter}`);
    await user.click(await screen.findByTestId('escalate-button'));
    await user.click(await screen.findByTestId('escalation-submit'));
    expect(await screen.findByTestId('error-alert')).toHaveTextContent(
      /not available on this deployment/i,
    );
  });

  it('reports rate limiting and refuses a malformed answer', async () => {
    server.use(
      http.post('*/api/v1/qa', () =>
        HttpResponse.json(
          { title: 'Too Many Requests', status: 429, request_id: 'r-9' },
          { status: 429 },
        ),
      ),
    );
    const { user } = renderApp();
    await user.type(screen.getByTestId('question-input'), `${QUESTION}{Enter}`);
    expect(await screen.findByTestId('error-alert')).toHaveTextContent(/too many questions/i);

    server.use(http.post('*/api/v1/qa', () => HttpResponse.json({ status: 'validated' })));
    await user.click(screen.getByTestId('ask-button'));
    expect(await screen.findByTestId('error-alert')).toHaveTextContent(/cannot verify/i);
  });

  it('keeps a session history and copies the answer with its sources', async () => {
    const { user } = renderApp(); // user-event installs a clipboard stub on navigator
    await user.type(screen.getByTestId('question-input'), `${QUESTION}{Enter}`);
    await screen.findByTestId('answer-card');
    await user.click(screen.getByTestId('copy-answer'));
    await screen.findByText('Copied.');
    const copied = await navigator.clipboard.readText();
    expect(copied).toContain('Sources:');
    expect(copied).toContain('[1] Hand Hygiene in Health Care (WHO)');
    expect(copied).toContain('Not for clinical use');
    expect(screen.getByText('Copied.')).toBeInTheDocument();

    expect(screen.getAllByTestId('history-item')).toHaveLength(1);
    expect(sessionStorage.getItem('hcrag.history')).toContain(QUESTION);
    await user.click(screen.getByTestId('history-clear'));
    expect(screen.queryByTestId('history-item')).not.toBeInTheDocument();
  });

  it('restores the session history after a reload', async () => {
    const first = renderApp();
    await first.user.type(screen.getByTestId('question-input'), `${QUESTION}{Enter}`);
    await screen.findByTestId('answer-card');
    first.unmount();
    renderApp();
    expect(await screen.findAllByTestId('history-item')).toHaveLength(1);
    expect(screen.getByTestId('answer-card')).toBeInTheDocument();
  });
});
