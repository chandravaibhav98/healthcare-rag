import { expect, test } from '@playwright/test';

import { login } from './helpers';

test.describe('Admin workflows', () => {
  test('a reviewer approves an item from the review queue', async ({ page }) => {
    await login(page, 'reviewer');
    await page.goto('/admin/review');
    await expect(page.getByTestId('review-form')).toBeVisible();

    await page.getByTestId('verdict-approve').check();
    await expect(page.getByTestId('verdict-approve')).toBeChecked();
    await page.getByTestId('review-note').fill(`E2E approve ${Date.now().toString()}`);
    await page.getByTestId('review-submit').click();
    await expect(page.getByTestId('review-saved')).toBeVisible();

    // The reviewed item shows up under "Reviewed". Question text is not asserted on: other
    // specs (and --repeat-each) can leave duplicate pending questions in the queue.
    await page.getByTestId('queue-status').selectOption('reviewed');
    await expect(page.getByTestId('queue-list')).toContainText('approve');
  });

  test('a settings change is versioned and appears in the audit log', async ({ page }) => {
    const comment = `E2E settings change ${Date.now().toString()}`;
    await login(page, 'admin');
    await page.goto('/admin/settings');
    const floor = page.getByTestId('cfg-retrieval_floor');
    await expect(floor).toHaveValue(/\d/);
    const original = await floor.inputValue();

    const save = async (value: string, why: string) => {
      await floor.fill(value);
      await page.getByTestId('cfg-comment').fill(why);
      await page.getByTestId('config-save').click();
      await expect(page.getByTestId('config-saved')).toBeVisible();
    };
    await save('0.14', comment);
    await expect(page.getByTestId('config-version')).toContainText(comment);

    await page.goto('/admin/audit');
    await page.getByTestId('audit-action').fill('config.');
    await page.getByTestId('audit-apply').click();
    const row = page.getByTestId('audit-row').filter({ hasText: comment });
    await expect(row).toBeVisible();
    await expect(row).toContainText('admin@example.org');

    // Leave the shared stack as we found it.
    await page.goto('/admin/settings');
    await save(original, 'E2E restore');
  });

  test('the query explorer filters and opens the detail drawer', async ({ page }) => {
    await login(page, 'reviewer');
    await page.goto('/admin/queries');
    await page.getByTestId('filter-status').selectOption('needs_review');
    await page.getByTestId('filter-apply').click();
    await expect(page.getByTestId('query-row').first()).toBeVisible();
    await expect(page.getByTestId('queries-table')).not.toContainText('Validated');
    await page.getByTestId('query-row').first().getByRole('button').first().click();
    await expect(page.getByTestId('query-drawer')).toContainText('Request ID');
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('query-drawer')).toHaveCount(0);
  });
});
