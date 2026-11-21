/**
 * The recorded product demo (plan Phase 11): one paced walkthrough, ten chapters.
 *
 * Run it through scripts/demo-record.{sh,ps1}, which starts a freshly seeded stack with a
 * second index version (E2E_CANDIDATE_INDEX=1), checks the index version, and turns the
 * video into an MP4 with chapter markers. `npm --prefix e2e run demo` runs it bare.
 *
 * The questions were chosen against the deterministic index (6ce73ffaf982), so they give
 * the same outcome every time: two validated answers (one citing three organisations)
 * and one near-domain question that the assistant declines to answer. Every step still
 * asserts what it shows, so a recording of a broken app fails instead of being published.
 */
import { expect, test, type Page } from '@playwright/test';

import {
  Chapters,
  hideCaption,
  installOverlay,
  pointAt,
  showCaption,
  spotlight,
  typeSlowly,
} from './captions';

const PASSWORD = process.env.E2E_PASSWORD ?? 'e2e-password-123';
const ADMIN = process.env.DEMO_ADMIN_EMAIL ?? 'admin@example.org';
/** Set by demo-record from the index it built; the recording must use that index. */
const EXPECTED_INDEX = process.env.DEMO_EXPECT_INDEX;

const PPE_QUESTION = 'When should an N95 respirator be discarded?';
const COLD_CHAIN_QUESTION = 'What temperature range should refrigerated vaccines be stored at?';
const UNSUPPORTED_QUESTION = 'Which antibiotic should be used for community-acquired pneumonia?';
const TOTAL = 10;

let chapters: Chapters;

async function chapter(page: Page, n: number, title: string, text: string, ms?: number) {
  chapters.mark(`${n.toString()}. ${title}`);
  await showCaption(page, { step: `${n.toString()} / ${TOTAL.toString()}`, title, text }, ms);
}

async function ask(page: Page, question: string, historyCount: number): Promise<void> {
  await typeSlowly(page.getByTestId('question-input'), question);
  await page.getByTestId('question-input').press('Enter');
  await expect(page.getByTestId('history-item')).toHaveCount(historyCount);
  await expect(page.getByTestId('answer-card')).toBeVisible();
}

async function nav(page: Page, label: string): Promise<void> {
  await page.getByTestId('admin-nav').getByRole('link', { name: label }).click();
}

test.beforeAll(async ({ playwright }, testInfo) => {
  // One evaluation before the camera rolls, so the trend chart has a first point and
  // the run started on camera adds the second.
  const api = await playwright.request.newContext({
    baseURL: testInfo.project.use.baseURL,
  });
  const ready = (await (await api.get('/readyz')).json()) as { index_version: string };
  if (EXPECTED_INDEX)
    expect(ready.index_version, 'demo must run on the built index').toBe(EXPECTED_INDEX);
  const login = await api.post('/api/v1/auth/login', {
    data: { email: ADMIN, password: PASSWORD },
  });
  expect(login.status()).toBe(200);
  const { access_token: token } = (await login.json()) as { access_token: string };
  const headers = { authorization: `Bearer ${token}` };
  const runs = (await (await api.get('/api/v1/admin/eval-runs', { headers })).json()) as {
    items: { status: string }[];
  };
  if (!runs.items.some((r) => r.status === 'succeeded')) {
    expect((await api.post('/api/v1/admin/eval-runs', { headers })).status()).toBe(202);
    await expect
      .poll(
        async () => {
          const body = (await (await api.get('/api/v1/admin/eval-runs', { headers })).json()) as {
            items: { status: string }[];
          };
          return body.items[0]?.status;
        },
        { timeout: 120_000, intervals: [1000] },
      )
      .toBe('succeeded');
  }
  await api.dispose();
});

test('Healthcare Guidelines RAG Assistant: product demo', async ({ page }, testInfo) => {
  chapters = new Chapters(Date.now());
  await installOverlay(page);

  await test.step('1. Landing page and disclaimer', async () => {
    await page.goto('/');
    await expect(page.getByTestId('clinical-disclaimer')).toBeVisible();
    await chapter(
      page,
      1,
      'A citation-first assistant for clinical guidelines',
      'Answers come only from indexed WHO-, NIH- and CDC-style guidance. This corpus is synthetic: not for clinical use.',
      4500,
    );
    await spotlight(page.getByTestId('clinical-disclaimer'), 2200);
  });

  await test.step('2. PPE question → validated', async () => {
    await chapter(
      page,
      2,
      'Ask a PPE question',
      'Retrieval is hybrid (BM25 + dense vectors); the answer is extracted, never invented.',
    );
    await ask(page, PPE_QUESTION, 1);
    await expect(page.getByTestId('status-badge')).toHaveText(/validated/i);
    await showCaption(page, {
      step: '2 / 10',
      title: 'Validated, with citations',
      text: 'Every sentence carries a [n] marker that points at the guideline section it came from.',
    });
    await spotlight(page.getByTestId('status-badge'), 1500);
    await spotlight(page.getByTestId('answer-text'), 2200);
    // The confidence breakdown opens on focus (keyboard-accessible, WCAG 1.4.13).
    await page.getByTestId('confidence-meter').focus();
    await expect(page.getByTestId('signal-breakdown').first()).toBeVisible();
    await showCaption(
      page,
      {
        step: '2 / 10',
        title: 'Confidence is a blend of signals that can fail',
        text: 'Token coverage, query support and retrieval strength, plus a hard check that every number is in the evidence.',
      },
      4000,
    );
    await page.keyboard.press('Escape');
  });

  await test.step('3. Evidence panel', async () => {
    await chapter(
      page,
      3,
      'Check the evidence',
      'Open a citation: the cited text, with the words it shares with the answer highlighted.',
    );
    const chip = page.locator('[data-testid^="citation-chip-"]').first();
    await pointAt(chip);
    await chip.click();
    const panel = page.getByTestId('evidence-panel');
    await expect(panel).toBeVisible();
    expect(await panel.locator('[data-testid="evidence-text"] mark').count()).toBeGreaterThan(1);
    await spotlight(panel.getByTestId('evidence-text'), 3000);
    await spotlight(panel.getByTestId('evidence-overlap'), 1800);
    const numbers = panel.getByTestId('number-checks');
    if (await numbers.isVisible()) await spotlight(numbers, 2000);
  });

  await test.step('4. Cold-chain question → multi-source', async () => {
    await chapter(
      page,
      4,
      'Vaccine cold chain',
      'A question whose answer spans three organisations’ guidance.',
    );
    await ask(page, COLD_CHAIN_QUESTION, 2);
    await expect(page.getByTestId('status-badge')).toHaveText(/validated/i);
    await expect(page.getByTestId('answer-text')).toContainText('°C');
    const list = page.getByTestId('citation-list');
    await expect(list).toContainText('WHO');
    await expect(list).toContainText('CDC');
    await expect(list).toContainText('NIH');
    await showCaption(page, {
      step: '4 / 10',
      title: 'WHO, CDC and NIH sources agree',
      text: 'The numbers (2–8 °C) passed the numeric check: each one appears in its cited source.',
    });
    await spotlight(list, 3000);
  });

  await test.step('5. Unsupported question → needs review', async () => {
    await chapter(
      page,
      5,
      'When the evidence is not there, it abstains',
      'A clinical question the guideline set does not cover.',
    );
    await ask(page, UNSUPPORTED_QUESTION, 3);
    await expect(page.getByTestId('status-badge')).toHaveText(/needs review/i);
    await expect(page.getByTestId('abstention')).toBeVisible();
    await showCaption(page, {
      step: '5 / 10',
      title: 'No answer is better than a weakly supported one',
      text: 'The best candidate sources are still shown, and the user can escalate to a reviewer.',
    });
    await spotlight(page.getByTestId('abstention'), 2500);
    await page.getByTestId('escalate-button').click();
    await typeSlowly(
      page.getByTestId('escalation-note'),
      'Not covered by our guidelines? Please check.',
    );
    await page.getByTestId('escalation-submit').click();
    await expect(page.getByTestId('escalation-done')).toBeVisible();
    await page.waitForTimeout(1200);
  });

  await test.step('6. Admin overview', async () => {
    await page.goto('/login');
    await chapter(
      page,
      6,
      'The admin dashboard',
      'Reviewers and admins sign in to monitor quality and act on what the assistant withheld.',
    );
    await typeSlowly(page.getByTestId('login-email'), ADMIN);
    await page.getByTestId('login-password').fill(PASSWORD);
    await page.getByTestId('login-submit').click();
    await expect(page.getByTestId('current-user')).toContainText('(admin)');
    await page.goto('/admin');
    await expect(page.getByTestId('kpi-total')).toBeVisible();
    await showCaption(page, {
      step: '6 / 10',
      title: 'Overview: volume, pass rate, confidence, abstentions, latency',
      text: 'A week of seeded traffic plus the questions just asked.',
    });
    for (const id of ['kpi-total', 'kpi-pass-rate', 'kpi-abstention', 'kpi-p95']) {
      await spotlight(page.getByTestId(id).locator('..'), 900);
    }
  });

  await test.step('7. Review queue → approve and promote', async () => {
    await nav(page, 'Review queue');
    await expect(page.getByTestId('queue-list')).toBeVisible();
    await chapter(
      page,
      7,
      'Review queue',
      'The abstained question is waiting, with its candidate answer and evidence.',
    );
    const item = page.getByTestId('queue-item').filter({ hasText: UNSUPPORTED_QUESTION }).first();
    await expect(item).toBeVisible();
    await item.click();
    await expect(page.getByTestId('review-question')).toContainText(UNSUPPORTED_QUESTION);
    await spotlight(page.getByTestId('review-detail'), 2000);
    await page.getByTestId('verdict-approve').check();
    await page.getByTestId('promote-to-gold').check();
    await typeSlowly(
      page.getByTestId('review-note'),
      'Correct to withhold: out of scope for this corpus.',
    );
    await showCaption(page, {
      step: '7 / 10',
      title: 'Approve the abstention and promote it to the gold set',
      text: 'Reviewed items become evaluation candidates: the feedback loop closes.',
    });
    await page.getByTestId('review-submit').click();
    await expect(page.getByTestId('review-saved')).toBeVisible();
    await page.waitForTimeout(1500);
  });

  await test.step('8. Evaluation', async () => {
    await nav(page, 'Evaluation');
    await expect(page.getByTestId('chart-eval-trend')).toBeVisible();
    await chapter(
      page,
      8,
      'Evaluation',
      'Precision@5 and validation pass rate on the dev questions, plus the threshold sweep.',
    );
    await spotlight(page.getByTestId('chart-eval-trend'), 2200);
    await spotlight(page.getByTestId('chart-threshold-sweep'), 2500);
    const runs = await page.getByTestId('eval-run-row').count();
    await showCaption(page, {
      step: '8 / 10',
      title: 'Run an evaluation now',
      text: 'Same code as the CI gate, on the active index and live settings.',
    });
    await page.getByTestId('run-evaluation').click();
    await expect(page.getByTestId('run-evaluation')).toHaveText(/Run evaluation/, {
      timeout: 120_000,
    });
    await expect(page.getByTestId('eval-run-row')).toHaveCount(runs + 1);
    await spotlight(page.getByTestId('eval-runs-table'), 2000);
  });

  await test.step('9. Index versions → activate and roll back', async () => {
    await nav(page, 'Index & corpus');
    const table = page.getByTestId('versions-table');
    await expect(table).toBeVisible();
    await chapter(
      page,
      9,
      'Index versions',
      'Each version is named by the hash of its corpus and build settings: rebuilds are byte-identical.',
    );
    await spotlight(table, 2500);
    const activate = page.getByTestId('activate-version');
    if ((await activate.count()) > 0) {
      const active = page.getByTestId('version-row').filter({ hasText: 'Active' });
      const original = (await active.locator('td').first().innerText())
        .replace('Active', '')
        .trim();
      await showCaption(page, {
        step: '9 / 10',
        title: 'Activate a candidate index',
        text: 'Hash-verified, then hot-swapped: requests in flight finish on the old index.',
      });
      await activate.first().click();
      await page.getByTestId('activate-confirm').click();
      await expect(active).not.toContainText(original);
      await spotlight(active, 1800);
      await showCaption(page, {
        step: '9 / 10',
        title: 'Rolling back is the same click',
        text: `Back to ${original}.`,
      });
      await page
        .getByTestId('version-row')
        .filter({ hasText: original })
        .getByTestId('activate-version')
        .click();
      await page.getByTestId('activate-confirm').click();
      await expect(active).toContainText(original);
      await spotlight(active, 1500);
    }
  });

  await test.step('10. Settings → audit log', async () => {
    await nav(page, 'Settings');
    const threshold = page.getByTestId('cfg-threshold');
    await expect(threshold).toHaveValue(/\d/);
    await chapter(
      page,
      10,
      'Settings are versioned and audited',
      'Raise the confidence threshold and preview its effect from the last evaluation.',
    );
    await typeSlowly(threshold, '0.65');
    await spotlight(page.getByTestId('impact-preview'), 2500);
    await typeSlowly(page.getByTestId('cfg-comment'), 'Demo: stricter threshold for the pilot');
    await page.getByTestId('config-save').click();
    await expect(page.getByTestId('config-saved')).toBeVisible();
    await nav(page, 'Audit log');
    await page.getByTestId('audit-action').fill('config.');
    await page.getByTestId('audit-apply').click();
    const row = page
      .getByTestId('audit-row')
      .filter({ hasText: 'Demo: stricter threshold' })
      .first();
    await expect(row).toBeVisible();
    await showCaption(page, {
      step: '10 / 10',
      title: 'Every change has an owner and a reason',
      text: 'Who, what, when and why: in the audit log, for every setting, review and index change.',
    });
    await spotlight(row, 2500);
  });

  chapters.mark('Summary');
  await showCaption(
    page,
    {
      title: 'Citation-first · evidence-validated · abstains when unsure',
      text: 'FastAPI · React · FAISS + BM25 · PostgreSQL · Docker · Kubernetes · CI/CD',
    },
    5000,
  );
  await hideCaption(page);
  await page.waitForTimeout(500);
  chapters.write(testInfo.outputPath('chapters.json'));
});
