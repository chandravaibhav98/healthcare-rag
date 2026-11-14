// Phase 6 exit check (plan §4 Phase 6): drive every screen against a REAL running stack,
// run axe-core (WCAG 2.0–2.2 A/AA + best practices, colour contrast included) in light and
// dark mode, then Lighthouse accessibility and best-practices on every route.
//
// It CHANGES data (an escalation, a review, a settings change, an evaluation run), so run
// it only against a freshly seeded development stack:
//
//   scripts/seed.sh --reset --demo && scripts/dev.sh        # API :8000, web :5173
//   cd e2e/audit && npm ci && BASE_URL=http://localhost:5173 CHROME_PATH=/path/to/chrome npm run audit
//
// Exit code 1 if any flow fails, axe finds a serious/critical violation, or a Lighthouse
// accessibility score is below 95.
import { chromium } from 'playwright-core';
import { AxeBuilder } from '@axe-core/playwright';
import lighthouse from 'lighthouse';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const BASE = process.env.BASE_URL ?? 'http://localhost:5173';
const CHROME = process.env.CHROME_PATH ?? '/usr/bin/google-chrome';
const OUT = process.env.OUT_DIR ?? fileURLToPath(new URL('./results/', import.meta.url));
const ADMIN = {
  email: process.env.ADMIN_EMAIL ?? 'admin@example.org',
  password: process.env.ADMIN_PASSWORD ?? 'change-me-admin',
};
const USER = {
  email: process.env.USER_EMAIL ?? 'user@example.org',
  password: process.env.USER_PASSWORD ?? ADMIN.password,
};
const PORT = Number(process.env.CDP_PORT ?? 9333);
fs.mkdirSync(OUT, { recursive: true });
const out = { axe: [], lighthouse: [], flows: [] };
const ctx = await chromium.launchPersistentContext(
  fs.mkdtempSync(path.join(os.tmpdir(), 'ui-audit-')),
  {
    executablePath: CHROME,
    headless: true,
    args: [`--remote-debugging-port=${PORT}`, '--no-sandbox'],
    viewport: { width: 1366, height: 900 },
  },
);
const page = ctx.pages()[0] ?? (await ctx.newPage());
const consoleErrors = [];
page.on('console', (m) => {
  if (m.type() === 'error') consoleErrors.push(m.text());
});
page.on('pageerror', (e) => consoleErrors.push(String(e)));

async function axe(name) {
  for (const theme of ['light', 'dark']) {
    await page.evaluate(
      (t) => document.documentElement.classList.toggle('dark', t === 'dark'),
      theme,
    );
    await page.waitForTimeout(150);
    const r = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'])
      .analyze();
    const v = r.violations.map((x) => ({
      id: x.id,
      impact: x.impact,
      n: x.nodes.length,
      sample: x.nodes
        .slice(0, 2)
        .map((n) => n.target.join(' ') + ' :: ' + (n.failureSummary || '').split('\n')[1]),
    }));
    out.axe.push({ page: name, theme, violations: v });
  }
  await page.evaluate(() => document.documentElement.classList.remove('dark'));
}
const step = async (name, fn) => {
  try {
    await fn();
    out.flows.push([name, 'ok']);
  } catch (e) {
    out.flows.push([name, 'FAIL ' + String(e).split('\n')[0]]);
    await page.screenshot({
      path: `${OUT}fail-${name.replace(/\W+/g, '_')}.png`,
    });
  }
};
const tid = (id) => page.getByTestId(id);

await step('assistant: validated answer', async () => {
  await page.goto(BASE + '/');
  await tid('question-input').fill('How long should hand hygiene with alcohol-based handrub take?');
  await page.keyboard.press('Enter');
  await tid('answer-card').waitFor();
  const status = await tid('status-badge').innerText();
  if (!/validated/i.test(status)) throw new Error('expected validated, got ' + status);
  await tid('evidence-panel').waitFor();
  const marks = await page.locator('[data-testid=evidence-text] mark').count();
  if (marks < 2) throw new Error('too few highlights: ' + marks);
  await tid('confidence-meter').focus();
  await page.getByTestId('signal-breakdown').first().waitFor({ timeout: 3000 });
  await page.keyboard.press('Escape'); // tooltip closes on Escape (WCAG 1.4.13)
  await page.getByTestId('signal-breakdown').first().waitFor({ state: 'detached', timeout: 3000 });
  await page.screenshot({
    path: OUT + 'assistant-validated.png',
    fullPage: true,
  });
});
await axe('assistant (validated)');
await step('assistant: abstention + escalate', async () => {
  await tid('question-input').fill('How do I bake sourdough bread at home?');
  await tid('ask-button').click();
  await tid('abstention').waitFor();
  await tid('escalate-button').click();
  await tid('escalation-note').fill('Please check the vaccine guidance');
  await axe('escalate dialog');
  await tid('escalation-submit').click();
  await tid('escalation-done').waitFor();
  await page.screenshot({
    path: OUT + 'assistant-abstained.png',
    fullPage: true,
  });
});
await axe('assistant (abstained)');
await step('login as admin', async () => {
  await page.goto(BASE + '/admin');
  await tid('login-email').waitFor();
  await axe('login');
  await tid('login-email').fill(ADMIN.email);
  await tid('login-password').fill(ADMIN.password);
  await tid('login-submit').click();
  await tid('page-overview').waitFor();
  await tid('kpi-total').waitFor();
});
await step('overview', async () => {
  const total = await tid('kpi-total').innerText();
  if (Number(total) < 60) throw new Error('kpi total ' + total);
  await page.locator('[data-testid=chart-trend] svg').first().waitFor();
  await page.screenshot({ path: OUT + 'overview.png', fullPage: true });
});
await axe('overview');
await step('review queue: escalated item present, approve it', async () => {
  await page.goto(BASE + '/admin/review');
  await tid('review-detail').waitFor();
  const items = await tid('queue-item').allInnerTexts();
  if (!items.some((t) => /Escalated/.test(t))) throw new Error('escalated item missing');
  await axe('review queue');
  await tid('verdict-approve').check();
  await tid('review-submit').click();
  await tid('review-saved').waitFor();
});
await step('query explorer: filter + drawer', async () => {
  await page.goto(BASE + '/admin/queries');
  await tid('query-row').first().waitFor();
  await tid('filter-status').selectOption('needs_review');
  await tid('filter-apply').click();
  await page.waitForTimeout(500);
  const rows = await tid('query-row').allInnerTexts();
  if (rows.some((r) => /Validated/.test(r))) throw new Error('filter not applied');
  await tid('query-row').first().getByRole('button').first().click();
  await tid('query-drawer').waitFor();
  await axe('query drawer');
  await page.keyboard.press('Escape');
});
await axe('query explorer');
await step('evaluation: run to completion', async () => {
  await page.goto(BASE + '/admin/evaluation');
  await tid('run-evaluation').click();
  await page.waitForFunction(
    () => document.querySelector('[data-testid=eval-run-row]')?.textContent?.includes('succeeded'),
    null,
    { timeout: 60000 },
  );
  await tid('chart-threshold-sweep').waitFor({ timeout: 10000 });
  await tid('low-confidence-table').waitFor();
  await page.screenshot({ path: OUT + 'evaluation.png', fullPage: true });
});
await axe('evaluation');
await step('index & corpus', async () => {
  await page.goto(BASE + '/admin/index');
  await tid('version-row').first().waitFor();
  await tid('document-row').first().waitFor();
  const docs = await tid('documents-table').innerText();
  if (!/(cdc|who|nih)-/.test(docs)) throw new Error('documents missing');
});
await axe('index');
await step('settings: impact preview + save', async () => {
  await page.goto(BASE + '/admin/settings');
  await tid('preview-pass-rate').waitFor();
  await tid('cfg-threshold').fill('0.65');
  await tid('cfg-comment').fill('UI audit: try 0.65');
  await tid('config-save').click();
  await tid('config-saved').waitFor();
  await page.screenshot({ path: OUT + 'settings.png', fullPage: true });
});
await axe('settings');
await step('audit log shows the UI actions', async () => {
  await page.goto(BASE + '/admin/audit');
  await tid('audit-row').first().waitFor();
  const text = await tid('audit-table').innerText();
  for (const a of ['config.update', 'review.create', 'query.escalated', 'eval.start', 'auth.login'])
    if (!text.includes(a)) throw new Error('missing ' + a);
});
await axe('audit log');
await step('mobile layout (390px) has no horizontal page overflow', async () => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const p of ['/', '/admin', '/admin/queries']) {
    await page.goto(BASE + p);
    await page.waitForTimeout(600);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    if (overflow > 1) throw new Error(`${p} overflows by ${overflow}px`);
  }
  await page.screenshot({ path: OUT + 'mobile-admin.png', fullPage: false });
  await page.setViewportSize({ width: 1366, height: 900 });
});
await step('403 for a plain user', async () => {
  await page.goto(BASE + '/');
  await tid('logout').click();
  await tid('nav-login').waitFor();
  await page.goto(BASE + '/login');
  await tid('login-email').fill(USER.email);
  await tid('login-password').fill(USER.password);
  await tid('login-submit').click();
  await page.waitForTimeout(500);
  await page.goto(BASE + '/admin');
  await tid('page-403').waitFor();
});
await axe('403');

// Lighthouse (accessibility, best practices) in the same profile: the refresh cookie
// restores the admin session on each page load.
await page.goto(BASE + '/login');
await tid('login-email').fill(ADMIN.email);
await tid('login-password').fill(ADMIN.password);
await tid('login-submit').click();
await tid('page-overview').waitFor();
for (const p of [
  '/',
  '/login',
  '/admin',
  '/admin/review',
  '/admin/queries',
  '/admin/evaluation',
  '/admin/index',
  '/admin/settings',
  '/admin/audit',
]) {
  const r = await lighthouse(BASE + p, {
    port: PORT,
    output: 'json',
    onlyCategories: ['accessibility', 'best-practices'],
    formFactor: 'desktop',
    screenEmulation: { disabled: true },
    logLevel: 'error',
  });
  const lhr = r.lhr;
  const failed = Object.values(lhr.audits)
    .filter(
      (a) => a.score === 0 && lhr.categories.accessibility.auditRefs.some((ref) => ref.id === a.id),
    )
    .map((a) => a.id);
  out.lighthouse.push({
    page: p,
    accessibility: Math.round(lhr.categories.accessibility.score * 100),
    bestPractices: Math.round(lhr.categories['best-practices'].score * 100),
    failed,
  });
}
out.consoleErrors = consoleErrors;
fs.writeFileSync(OUT + 'result.json', JSON.stringify(out, null, 2));
await ctx.close();
console.log(JSON.stringify(out.flows));
console.log(JSON.stringify(out.lighthouse));
const serious = out.axe.flatMap((a) =>
  a.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${a.page}/${a.theme}: ${v.id} (${v.n}) ${v.sample.join(' | ')}`),
);
console.log('axe serious/critical:', serious.length);
serious.forEach((s) => console.log('  ' + s));
const minor = out.axe.flatMap((a) =>
  a.violations
    .filter((v) => !(v.impact === 'serious' || v.impact === 'critical'))
    .map((v) => `${a.page}/${a.theme}: ${v.id}/${v.impact} (${v.n})`),
);
console.log('axe moderate/minor:', [...new Set(minor)].length);
[...new Set(minor)].slice(0, 30).forEach((s) => console.log('  ' + s));
console.log('console errors:', consoleErrors.length, consoleErrors.slice(0, 5));

const failedFlows = out.flows.filter(([, r]) => r !== 'ok').length;
const lowLighthouse = out.lighthouse.filter((l) => l.accessibility < 95).length;
process.exit(failedFlows || serious.length || lowLighthouse ? 1 : 0);
