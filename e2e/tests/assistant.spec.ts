import { expect, test } from '@playwright/test';

import { ANSWERABLE, ask, OFF_TOPIC } from './helpers';

test.describe('Query Assistant', () => {
  test('a guideline question is answered, validated and cited', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByTestId('clinical-disclaimer')).toContainText('Not for clinical use');
    await ask(page, ANSWERABLE);

    await expect(page.getByTestId('status-badge')).toHaveText(/validated/i);
    const meter = page.getByRole('meter', { name: /confidence/i });
    expect(Number(await meter.getAttribute('aria-valuenow'))).toBeGreaterThanOrEqual(60);
    await expect(page.getByTestId('answer-text')).toContainText(/seconds/i);
    await expect(page.locator('[data-testid^="citation-chip-"]').first()).toBeVisible();
  });

  test('the evidence panel shows the cited text with shared words highlighted', async ({
    page,
  }) => {
    await page.goto('/');
    await ask(page, ANSWERABLE);
    await page.locator('[data-testid^="citation-chip-"]').first().click();

    const panel = page.getByTestId('evidence-panel');
    await expect(panel).toBeVisible();
    expect(await panel.locator('[data-testid="evidence-text"] mark').count()).toBeGreaterThan(1);
    await expect(panel.getByTestId('evidence-overlap')).toContainText(/key words/);

    // The signal breakdown opens from the keyboard and closes with Escape (WCAG 1.4.13).
    await page.getByTestId('confidence-meter').focus();
    await expect(page.getByTestId('signal-breakdown').first()).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('signal-breakdown')).toHaveCount(0);
  });

  test('an out-of-scope question abstains, shows why, and can be escalated', async ({ page }) => {
    await page.goto('/');
    await ask(page, OFF_TOPIC);
    await expect(page.getByTestId('status-badge')).toHaveText(/needs review/i);
    await expect(page.getByTestId('abstention')).toContainText(/no validated answer/i);

    await page.getByTestId('escalate-button').click();
    await page.getByTestId('escalation-note').fill('E2E: please check');
    await page.getByTestId('escalation-submit').click();
    await expect(page.getByTestId('escalation-done')).toContainText(/sent to the reviewers/i);
  });

  test('the session history keeps earlier answers', async ({ page }) => {
    await page.goto('/');
    await ask(page, ANSWERABLE);
    await ask(page, OFF_TOPIC);
    await expect(page.getByTestId('history-item')).toHaveCount(2);
    await page.getByTestId('history-item').nth(1).click();
    await expect(page.getByTestId('status-badge')).toHaveText(/validated/i);
  });
});
