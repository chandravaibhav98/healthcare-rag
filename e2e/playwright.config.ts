/**
 * Playwright functional E2E (plan Phase 7).
 *
 * By default the config starts its own stack: a disposable seeded API
 * (backend/scripts/e2e_server.py) and the production build of the SPA served by
 * `vite preview`, which proxies /api to that API (same origin, like nginx in Phase 8).
 * Set E2E_BASE_URL to test an already running stack instead (Docker, kind).
 *
 * Tests share one seeded database and run serially (workers: 1), so each test leaves
 * the data as it found it or only adds to it.
 */
import { defineConfig, devices } from '@playwright/test';

const API_PORT = Number(process.env.E2E_API_PORT ?? 8100);
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 4180);
const external = process.env.E2E_BASE_URL;
const chromePath = process.env.CHROME_PATH; // use an installed Chrome instead of the bundled one

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  expect: { timeout: 7_500 },
  reporter: process.env.CI
    ? [['list'], ['html', { open: 'never' }], ['junit', { outputFile: 'test-results/junit.xml' }]]
    : [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: external ?? `http://127.0.0.1:${WEB_PORT.toString()}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Recording needs Playwright's ffmpeg, which `playwright install chromium` downloads.
    // A local run on CHROME_PATH may not have it, so videos are a CI-only artifact.
    video: process.env.CI ? 'retain-on-failure' : 'off',
    testIdAttribute: 'data-testid',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        ...(chromePath ? { launchOptions: { executablePath: chromePath } } : {}),
      },
    },
  ],
  webServer: external
    ? undefined
    : [
        {
          command: `uv run --directory ../backend python scripts/e2e_server.py --port ${API_PORT.toString()}`,
          url: `http://127.0.0.1:${API_PORT.toString()}/readyz`,
          timeout: 120_000,
          reuseExistingServer: false,
          stdout: 'pipe',
        },
        {
          command: `npm --prefix ../frontend run -s build && npm --prefix ../frontend run -s preview -- --port ${WEB_PORT.toString()} --strictPort`,
          url: `http://127.0.0.1:${WEB_PORT.toString()}`,
          timeout: 120_000,
          reuseExistingServer: false,
          env: {
            VITE_DEV_API_TARGET: `http://127.0.0.1:${API_PORT.toString()}`,
          },
        },
      ],
});
