import { AxeBuilder } from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

import { ANSWERABLE, ask, login } from './helpers';

// Accessibility gate (closes OI-29): the Phase 6 browser audit's axe-core rules, run on
// every route in light and dark mode inside the CI E2E job. Any violation fails the build.
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'];

async function expectNoViolations(page: Page, name: string): Promise<void> {
  for (const theme of ['light', 'dark'] as const) {
    await page.evaluate(
      (t) => document.documentElement.classList.toggle('dark', t === 'dark'),
      theme,
    );
    const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    const summary = violations.map(
      (v) => `${v.id} (${v.impact ?? 'n/a'}): ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`,
    );
    expect(summary, `${name} [${theme}]`).toEqual([]);
  }
}

test.describe('Accessibility (axe-core, WCAG 2.2 AA)', () => {
  test('public pages', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByTestId('login-submit')).toBeVisible();
    await expectNoViolations(page, 'login');

    await page.goto('/');
    await ask(page, ANSWERABLE);
    await page.locator('[data-testid^="citation-chip-"]').first().click();
    await expect(page.getByTestId('evidence-panel')).toBeVisible();
    await expectNoViolations(page, 'assistant with evidence');
  });

  for (const route of [
    'admin',
    'admin/review',
    'admin/queries',
    'admin/evaluation',
    'admin/index',
    'admin/settings',
    'admin/audit',
  ]) {
    test(`/${route}`, async ({ page }) => {
      await login(page, 'admin');
      await page.goto(`/${route}`);
      await expect(page.locator('main h1')).toBeVisible();
      // Charts and tables load after the heading; wait until no request is in flight.
      await page.waitForLoadState('networkidle');
      await expectNoViolations(page, route);
    });
  }
});
