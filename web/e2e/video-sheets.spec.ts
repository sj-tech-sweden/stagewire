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

test('patch sheets show a video sheet for each device with its inputs and outputs', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Video Sheets ${Date.now()}` })).id as string;
  const switcher = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'ATEM Sheet', device_type: 'switcher' });
  const list = await post(request, headers, `/jobs/${jobId}/video-lists`, { name: 'Cameras' });
  const cam = await post(request, headers, `/jobs/${jobId}/video-lists/${list.id}/inputs`, { source_label: 'Cam 7 Balcony' });
  await post(request, headers, `/jobs/${jobId}/video-inputs/${cam.id}/patch-points`, { position: 0, device_id: switcher.id, patch_label: '3' });

  const loaded = page.waitForResponse((res) => res.url().includes('/video-patch-sheets') && res.ok());
  await page.goto(`/jobs/${jobId}/patch-sheets?view=video`);
  await loaded;
  await page.waitForLoadState('networkidle');
  await expect(page.getByText('Cam 7 Balcony', { exact: true })).toBeVisible();
});
