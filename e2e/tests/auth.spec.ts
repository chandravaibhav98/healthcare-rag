import { expect, test } from '@playwright/test';

import { apiToken, login } from './helpers';

test.describe('Sign-in per role and RBAC', () => {
  test('a user can ask but is denied the dashboard', async ({ page }) => {
    await login(page, 'user');
    await expect(page.getByTestId('nav-admin')).toHaveCount(0);
    await page.goto('/admin');
    await expect(page.getByTestId('page-403')).toBeVisible();
  });

  test('a reviewer sees the dashboard without admin-only parts', async ({ page }) => {
    await login(page, 'reviewer');
    await page.getByTestId('nav-admin').click();
    await expect(page.getByTestId('page-overview')).toBeVisible();
    const nav = page.getByTestId('admin-nav');
    await expect(nav).not.toContainText('Audit log');
    await page.goto('/admin/audit');
    await expect(page.getByTestId('page-403')).toBeVisible();
    await page.goto('/admin/settings');
    await expect(page.getByTestId('cfg-threshold')).toBeDisabled();
    await expect(page.getByTestId('config-save')).toHaveCount(0);
  });

  test('an admin sees every section, and the session survives a reload', async ({ page }) => {
    await login(page, 'admin');
    await page.goto('/admin/audit');
    await expect(page.getByTestId('page-audit')).toBeVisible();
    await page.reload(); // access token is in memory; the refresh cookie restores it
    await expect(page.getByTestId('audit-table')).toBeVisible();
  });

  test('anonymous visitors are sent to sign-in', async ({ page }) => {
    await page.goto('/admin/queries');
    await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  });

  test('the API enforces the same rules (RBAC denial below the UI)', async ({ request }) => {
    const reviewer = await apiToken(request, 'reviewer');
    const user = await apiToken(request, 'user');
    const config = {
      expected_version: 0,
      values: {},
      comment: 'should be denied',
    };

    const asReviewer = await request.put('/api/v1/admin/config', {
      headers: { Authorization: `Bearer ${reviewer}` },
      data: config,
    });
    expect(asReviewer.status()).toBe(403);
    expect(asReviewer.headers()['content-type']).toContain('application/problem+json');

    const asUser = await request.get('/api/v1/admin/stats', {
      headers: { Authorization: `Bearer ${user}` },
    });
    expect(asUser.status()).toBe(403);
    expect((await request.get('/api/v1/admin/stats')).status()).toBe(401);
  });
});
