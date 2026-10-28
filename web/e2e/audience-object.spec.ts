import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

test('the audience area is an object in the element palette that starts drawing', async ({ page, request }) => {
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  const headers = { Authorization: `Bearer ${token}` };
  const created = await request.post(`${API_BASE}/api/v1/jobs`, { headers, data: { title: `E2E Audience ${Date.now()}` } });
  const jobId = (await created.json()).id as string;

  const loaded = page.waitForResponse((res) => res.url().includes('/plot-elements') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.waitForLoadState('networkidle');

  await page.locator('.q-item', { hasText: 'Audience area' }).first().click();
  await expect(page.getByRole('button', { name: 'Finish area' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Finish area' })).toBeDisabled();
});
