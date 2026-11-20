import { expect, type APIRequestContext, type Page } from '@playwright/test';

export type Role = 'user' | 'reviewer' | 'admin';

/** Seeded by backend/scripts/e2e_server.py (override for an external stack). */
export const PASSWORD = process.env.E2E_PASSWORD ?? 'e2e-password-123';
export const email = (role: Role) => `${role}@example.org`;

export const ANSWERABLE = 'How long should hand hygiene with alcohol-based handrub take?';
export const OFF_TOPIC = 'How do I bake sourdough bread at home?';

export async function login(page: Page, role: Role): Promise<void> {
  await page.goto('/login');
  await page.getByTestId('login-email').fill(email(role));
  await page.getByTestId('login-password').fill(PASSWORD);
  await page.getByTestId('login-submit').click();
  await expect(page.getByTestId('current-user')).toContainText(`(${role})`);
}

export async function ask(page: Page, question: string): Promise<void> {
  await page.getByTestId('question-input').fill(question);
  await page.getByTestId('question-input').press('Enter');
  await expect(page.getByTestId('answer-card')).toBeVisible();
}

/** A bearer token for direct API calls (RBAC checks below the UI). */
export async function apiToken(request: APIRequestContext, role: Role): Promise<string> {
  const response = await request.post('/api/v1/auth/login', {
    data: { email: email(role), password: PASSWORD },
  });
  expect(response.status()).toBe(200);
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}
