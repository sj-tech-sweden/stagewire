import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

async function post(request: APIRequestContext, headers: Record<string, string>, path: string, data: object) {
  const res = await request.post(`${API_BASE}/api/v1${path}`, { headers, data });
  expect(res.status(), `${path}: ${await res.text()}`).toBeLessThan(300);
  return res.json();
}

async function seedJob(page: Page, request: APIRequestContext, title: string) {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title })).id as string;
  await post(request, headers, `/jobs/${jobId}/channel-lists`, { name: 'FOH Inputs' });
  await post(request, headers, `/jobs/${jobId}/video-lists`, { name: 'Cameras Lane' });
  return jobId;
}

test('on a computer the channel lists sit to the left of the content', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  const jobId = await seedJob(page, request, `E2E Layout Desk ${Date.now()}`);
  await page.goto(`/jobs/${jobId}`);
  await expect(page.getByText('FOH Inputs').first()).toBeVisible();
  const splitter = page.locator('.q-splitter').first();
  await expect(splitter).not.toHaveClass(/q-splitter--horizontal/);
});

test('on a phone the lists stay visible above the content, as a dropdown', async ({ page, request }) => {
  const jobId = await seedJob(page, request, `E2E Layout Phone ${Date.now()}`);
  await page.setViewportSize({ width: 390, height: 844 });
  const listsLoaded = page.waitForResponse((res) => res.url().includes('/channel-lists') && res.ok());
  await page.goto(`/jobs/${jobId}`);
  await listsLoaded;
  await expect(page.locator('.q-splitter').first()).toHaveClass(/q-splitter--horizontal/);
  await page.locator('.q-splitter .q-select').first().click();
  await expect(page.locator('.q-menu .q-item', { hasText: 'FOH Inputs' })).toBeVisible();
});

test('switching to Video shows the video lists in the same layout', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  const jobId = await seedJob(page, request, `E2E Layout Toggle ${Date.now()}`);
  await page.goto(`/jobs/${jobId}`);
  await page.getByRole('button', { name: 'Video', exact: true }).click();
  await expect(page.getByText('Cameras Lane').first()).toBeVisible();
  await expect(page).toHaveURL(/view=video/);
});
