import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ADMIN, API_BASE, ensureAdmin, login, enableStockwire } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

// Regression: the integration flags are loaded once after sign-in. If that single request failed,
// integration-only controls (here the stockwire catalog button) stayed hidden for the session. The
// first status request is failed on purpose. The job is opened from the list (an in-app navigation,
// not a reload), so only the retry can make the button appear.
test('a failed stockwire status request is retried, so integration controls still appear', async ({
  page,
  request,
}: {
  page: Page;
  request: APIRequestContext;
}) => {
  await enableStockwire(request);
  const title = `Retry E2E ${Date.now()}`;
  const loginRes = await request.post(`${API_BASE}/api/v1/auth/login`, { data: ADMIN });
  const token = (await loginRes.json()).access_token as string;
  await request.post(`${API_BASE}/api/v1/jobs`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { title },
  });

  let failedOnce = false;
  await page.route('**/api/v1/settings/stockwire', async (route) => {
    if (route.request().method() === 'GET' && !failedOnce) {
      failedOnce = true;
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"busy"}' });
      return;
    }
    await route.continue();
  });

  await login(page);
  await page.getByText(title).first().click();

  await expect(page.getByTestId('open-catalog')).toBeVisible();
  expect(failedOnce).toBe(true);
});
