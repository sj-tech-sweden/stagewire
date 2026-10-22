import { defineConfig, devices } from '@playwright/test';

// Start (or reuse) a local stack for the E2E run. We deliberately do NOT drop
// the database volume (`down -v` is avoided) so that running the test suite
// never destroys a developer's local data (users, jobs, SSO settings, ...).
// `up` is run in the foreground so Playwright can monitor the process; the
// database is migrated on API startup via `alembic upgrade head`.
export const STACK_COMPOSE =
  'docker compose -f ../docker-compose.yml down && docker compose -f ../docker-compose.yml up --build db valkey api web';

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL: 'http://localhost:9010',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: STACK_COMPOSE,
    url: 'http://localhost:9010',
    reuseExistingServer: true,
    timeout: 300_000,
  },
});
