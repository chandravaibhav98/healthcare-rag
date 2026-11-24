/**
 * Playwright: functional E2E (plan Phase 7) and the recorded demo (Phase 11).
 *
 * Two projects share one stack:
 *   e2e   tests/  fast, assertive; video and trace only for failures. `npm test`.
 *   demo  demo/   one paced, narrated walkthrough recorded at 1920×1080. `npm run demo`,
 *                 normally through scripts/demo-record.*, which also converts it to MP4.
 *
 * By default the config starts its own stack: a disposable seeded API
 * (backend/scripts/e2e_server.py) and the production build of the SPA served by
 * `vite preview`, which proxies /api to that API (same origin, like nginx in Phase 8).
 * Set E2E_BASE_URL to test an already running stack instead (Docker, kind).
 * E2E_CANDIDATE_INDEX=1 makes the API also build a second index version, which the
 * demo activates and rolls back.
 *
 * Tests share one seeded database and run serially (workers: 1), so each test leaves
 * the data as it found it or only adds to it.
 */
import { defineConfig, devices } from '@playwright/test';

const API_PORT = Number(process.env.E2E_API_PORT ?? 8100);
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 4180);
const external = process.env.E2E_BASE_URL;
const chromePath = process.env.CHROME_PATH; // use an installed Chrome instead of the bundled one
const launchOptions = chromePath ? { executablePath: chromePath } : {};
const candidate = process.env.E2E_CANDIDATE_INDEX === '1' ? ' --candidate-index' : '';

/** The demo's frame: 1080p viewport and video, so text stays sharp after H.264 encoding. */
const DEMO_SIZE = { width: 1920, height: 1080 };
/** Extra delay per browser action in the demo (ms): the viewer can follow every click. */
const DEMO_SLOW_MO = Number(process.env.DEMO_SLOW_MO ?? 120);

export default defineConfig({
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  timeout: 30_000,
  expect: { timeout: 7_500 },
  reporter: process.env.CI
    ? [['list'], ['html', { open: 'never' }], ['junit', { outputFile: 'test-results/junit.xml' }]]
    : [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: external ?? `http://127.0.0.1:${WEB_PORT.toString()}`,
    testIdAttribute: 'data-testid',
  },
  projects: [
    {
      name: 'e2e',
      testDir: './tests',
      retries: process.env.CI ? 1 : 0,
      use: {
        ...devices['Desktop Chrome'],
        launchOptions,
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        // Recording needs Playwright's ffmpeg, which `playwright install chromium`
        // downloads. A local run on CHROME_PATH may not have it, so failure videos are a
        // CI-only artifact.
        video: process.env.CI ? 'retain-on-failure' : 'off',
      },
    },
    {
      name: 'demo',
      testDir: './demo',
      retries: 0, // a retried recording would be a second, different video
      timeout: 10 * 60_000,
      expect: { timeout: 20_000 },
      use: {
        ...devices['Desktop Chrome'],
        viewport: DEMO_SIZE,
        deviceScaleFactor: 1,
        colorScheme: 'light',
        locale: 'en-GB',
        timezoneId: 'UTC',
        launchOptions: { ...launchOptions, slowMo: DEMO_SLOW_MO },
        video: { mode: 'on', size: DEMO_SIZE },
        trace: 'retain-on-failure',
      },
    },
  ],
  webServer: external
    ? undefined
    : [
        {
          command: `uv run --directory ../backend python scripts/e2e_server.py --port ${API_PORT.toString()}${candidate}`,
          url: `http://127.0.0.1:${API_PORT.toString()}/readyz`,
          timeout: 180_000,
          reuseExistingServer: false,
          stdout: 'pipe',
        },
        {
          // --host: bind the address Playwright polls. Without it Vite binds "localhost", which
          // Node can resolve to ::1 only, and the 127.0.0.1 readiness probe never answers
          // (manual test F-23: CI timed out after 120 s with the server running).
          command: `npm --prefix ../frontend run -s build && npm --prefix ../frontend run -s preview -- --host 127.0.0.1 --port ${WEB_PORT.toString()} --strictPort`,
          url: `http://127.0.0.1:${WEB_PORT.toString()}`,
          timeout: 120_000,
          reuseExistingServer: false,
          env: {
            VITE_DEV_API_TARGET: `http://127.0.0.1:${API_PORT.toString()}`,
          },
        },
      ],
});
