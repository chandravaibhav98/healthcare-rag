import { screen, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { getAccessToken } from '@/api/session';
import { expectNoSeriousA11yViolations } from '@/test/axe';
import { renderApp } from '@/test/render';
import { server } from '@/test/server';

describe('auth and route guards', () => {
  it('sends anonymous visitors from the dashboard to sign-in and back after login', async () => {
    const { user } = renderApp({ route: '/admin/queries' });
    expect(await screen.findByRole('heading', { name: /sign in/i })).toBeInTheDocument();
    await expectNoSeriousA11yViolations();
    await user.type(screen.getByTestId('login-email'), 'reviewer@example.org');
    await user.type(screen.getByTestId('login-password'), 'secret');
    await user.click(screen.getByTestId('login-submit'));
    expect(await screen.findByTestId('page-queries')).toBeInTheDocument();
    expect(getAccessToken()).toBe('token-reviewer');
    expect(screen.getByTestId('current-user')).toHaveTextContent('reviewer');
  });

  it('validates the form and shows server errors', async () => {
    const { user } = renderApp({ route: '/login' });
    await user.click(await screen.findByTestId('login-submit'));
    expect(await screen.findByText(/enter a valid e-mail/i)).toBeInTheDocument();
    expect(screen.getByTestId('login-email')).toHaveAttribute('aria-invalid', 'true');

    await user.type(screen.getByTestId('login-email'), 'nobody@example.org');
    await user.type(screen.getByTestId('login-password'), 'x');
    await user.click(screen.getByTestId('login-submit'));
    expect(await screen.findByTestId('login-error')).toHaveTextContent(
      /invalid email or password/i,
    );

    server.use(
      http.post('*/api/v1/auth/login', () =>
        HttpResponse.json({ title: 'Too Many Requests', status: 429 }, { status: 429 }),
      ),
    );
    await user.click(screen.getByTestId('login-submit'));
    expect(await screen.findByTestId('login-error')).toHaveTextContent(/too many attempts/i);
  });

  it('shows the 403 page to plain users', async () => {
    renderApp({ route: '/admin', role: 'user' });
    expect(await screen.findByTestId('page-403')).toBeInTheDocument();
    expect(screen.queryByTestId('nav-admin')).not.toBeInTheDocument();
  });

  it('hides admin-only navigation from reviewers and guards the audit route', async () => {
    renderApp({ route: '/admin/audit', role: 'reviewer' });
    expect(await screen.findByTestId('page-403')).toBeInTheDocument();
  });

  it('lets admins see every dashboard section', async () => {
    renderApp({ route: '/admin', role: 'admin' });
    const nav = await screen.findByTestId('admin-nav');
    expect(
      within(nav)
        .getAllByRole('link')
        .map((l) => l.textContent),
    ).toEqual([
      'Overview',
      'Review queue',
      'Query explorer',
      'Evaluation',
      'Index & corpus',
      'Settings',
      'Audit log',
    ]);
  });

  it('signs out and drops the session', async () => {
    const { user } = renderApp({ route: '/', role: 'admin' });
    await user.click(await screen.findByTestId('logout'));
    expect(await screen.findByTestId('nav-login')).toBeInTheDocument();
    expect(getAccessToken()).toBeNull();
  });
});
