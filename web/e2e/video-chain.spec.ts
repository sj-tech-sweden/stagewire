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

test('the whole patch flow of an input is set in the patch-flow editor, in order', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Chain ${Date.now()}` })).id as string;
  const cam = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'PTZ Cam 1', device_type: 'ptz_camera' });
  const bay = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Patchbay A', device_type: 'patchbay' });
  const atem = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'ATEM Switch', device_type: 'switcher' });
  const list = await post(request, headers, `/jobs/${jobId}/video-lists`, { name: 'Cameras' });
  const input = await post(request, headers, `/jobs/${jobId}/video-lists/${list.id}/inputs`, { source_label: 'Cam 1 FOH' });

  await page.goto(`/jobs/${jobId}?view=video`);
  await page.getByRole('button', { name: 'Edit input' }).first().click();

  await page.getByRole('button', { name: 'Add step' }).click();
  await page.getByLabel('Kind').nth(0).click();
  await page.locator('.q-menu .q-item', { hasText: 'PTZ camera' }).click();
  await page.getByLabel('Device').nth(0).click();
  await page.locator('.q-menu .q-item', { hasText: 'PTZ Cam 1' }).click();

  await page.getByRole('button', { name: 'Add step' }).click();
  await page.getByLabel('Device').nth(1).click();
  await page.locator('.q-menu .q-item', { hasText: 'Patchbay A' }).click();

  await page.getByRole('button', { name: 'Add step' }).click();
  await page.getByLabel('Kind').nth(2).click();
  await page.locator('.q-menu .q-item', { hasText: 'Switcher' }).click();
  await page.getByLabel('Device').nth(2).click();
  await page.locator('.q-menu .q-item', { hasText: 'ATEM Switch' }).click();

  await page.getByRole('button', { name: 'Save', exact: true }).click();

  await expect
    .poll(async () => {
      const lists = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/video-lists`, { headers })).json();
      return lists[0].inputs.find((i: { id: string }) => i.id === input.id).patch_points.map((p: { device_id: string }) => p.device_id);
    })
    .toEqual([cam.id, bay.id, atem.id]);
});
