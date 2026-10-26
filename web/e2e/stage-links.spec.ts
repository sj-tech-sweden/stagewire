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

test('any stage element can link to a channel and a video input, and the names show their list', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Stage Links ${Date.now()}` })).id as string;
  const sound = await post(request, headers, `/jobs/${jobId}/channel-lists`, { name: 'FOH' });
  await post(request, headers, `/jobs/${jobId}/channel-lists/${sound.id}/channels`, {
    channel_number: 1,
    source_label: 'Kick',
  });
  const video = await post(request, headers, `/jobs/${jobId}/video-lists`, { name: 'Cameras' });
  await post(request, headers, `/jobs/${jobId}/video-lists/${video.id}/inputs`, { source_label: 'Cam 1' });

  const loaded = page.waitForResponse((res) => res.url().includes('/video-lists') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.getByText('Custom', { exact: true }).first().click();

  await page.getByLabel('Linked channel').click();
  await expect(page.locator('.q-menu .q-item', { hasText: 'FOH · Ch 1: Kick' })).toBeVisible();
  await page.keyboard.press('Escape');

  await page.getByLabel('Linked video input').click();
  await page.locator('.q-menu .q-item', { hasText: 'Cameras · 1: Cam 1' }).click();
  await expect
    .poll(async () => {
      const res = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, { headers });
      const elements = (await res.json()) as Array<{ linked_video_input_id: string | null }>;
      return elements[0]?.linked_video_input_id ?? null;
    })
    .not.toBeNull();
});
