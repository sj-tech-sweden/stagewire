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

test('add a camera input and patch it through a switcher on the video page', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Video ${Date.now()}` })).id as string;
  const switcher = await post(request, headers, `/jobs/${jobId}/devices`, {
    name: 'ATEM Switcher',
    device_type: 'switcher',
  });

  await page.goto(`/jobs/${jobId}/video`);
  await page.getByLabel('New input list (e.g. Cameras)').fill('Cameras');
  await page.getByRole('button', { name: 'Add list' }).click();
  await page.getByRole('button', { name: 'Add input' }).click();
  await page.getByPlaceholder('e.g. Cam 1 FOH').fill('Cam 1 FOH');
  await page.getByPlaceholder('e.g. Cam 1 FOH').press('Tab');

  await page.getByPlaceholder('Pick a device').first().click();
  await page.locator('.q-menu .q-item', { hasText: 'ATEM Switcher' }).click();

  await expect
    .poll(async () => {
      const res = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/video-lists`, { headers });
      const lists = (await res.json()) as Array<{ inputs: Array<{ source_label: string; patch_points: Array<{ device_id: string }> }> }>;
      const input = lists[0]?.inputs[0];
      return input ? [input.source_label, input.patch_points[0]?.device_id] : null;
    })
    .toEqual(['Cam 1 FOH', switcher.id]);
});

test('a camera on the stage plot cables to its switcher', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Camera Cable ${Date.now()}` })).id as string;
  const switcher = await post(request, headers, `/jobs/${jobId}/devices`, {
    name: 'ATEM Switcher',
    device_type: 'switcher',
  });
  const list = await post(request, headers, `/jobs/${jobId}/video-lists`, { name: 'Cameras' });
  const input = await post(request, headers, `/jobs/${jobId}/video-lists/${list.id}/inputs`, {
    source_label: 'Cam 1 FOH',
  });
  await post(request, headers, `/jobs/${jobId}/video-inputs/${input.id}/patch-points`, {
    position: 0,
    device_id: switcher.id,
  });
  await post(request, headers, `/jobs/${jobId}/plot-elements`, {
    element_type: 'camera',
    label: 'Cam 1 FOH',
    position_x: 100,
    position_y: 300,
    width_cm: 40,
    height_cm: 30,
    linked_video_input_id: input.id,
  });

  await page.goto(`/jobs/${jobId}/stage-plot`);
  await expect(page.getByText('Cam 1 FOH → ATEM Switcher')).toBeVisible();
});
