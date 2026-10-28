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

test('on a phone the stage plot comes first and fits the screen width', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Phone Plot ${Date.now()}`, stage_width_cm: 1200, stage_height_cm: 700 })).id as string;
  await post(request, headers, `/jobs/${jobId}/plot-elements`, { element_type: 'performer', label: 'Singer', position_x: 100, position_y: 100, width_cm: 60, height_cm: 60 });

  await page.setViewportSize({ width: 390, height: 844 });
  const loaded = page.waitForResponse((res) => res.url().includes('/plot-elements') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.waitForLoadState('networkidle');

  const canvas = await page.locator('canvas').first().boundingBox();
  const palette = await page.getByText('Elements', { exact: true }).boundingBox();
  expect(canvas && palette).toBeTruthy();
  expect(canvas!.y).toBeLessThan(palette!.y);
  expect(canvas!.x + canvas!.width).toBeLessThanOrEqual(390);
});
