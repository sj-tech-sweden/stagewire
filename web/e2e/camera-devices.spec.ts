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

test('camera values can be entered on the device and a lens shows only its focal range', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Camera Devices ${Date.now()}` })).id as string;
  const camera = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'PTZ 1', device_type: 'camera' });
  const lens = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Zoom 12x', device_type: 'lens' });

  await page.goto(`/jobs/${jobId}/devices?device=${camera.id}`);
  await expect(page.getByLabel('Sensor width (mm)')).toBeVisible();
  await page.getByLabel('Sensor width (mm)').fill('8.8');
  await page.getByLabel('Focal length, shortest (mm)').fill('4');
  await page.getByLabel('Focal length, longest (mm)').fill('48');
  await page.getByLabel('Maximum useful distance (m)').fill('15');
  const saved = page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes(`/devices/${camera.id}`));
  await page.getByRole('button', { name: /save/i }).click();
  await saved;

  const device = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json();
  const updated = device.find((d: { id: string }) => d.id === camera.id);
  expect(updated).toMatchObject({ sensor_width_mm: 8.8, focal_min_mm: 4, focal_max_mm: 48, max_distance_m: 15 });

  await page.goto(`/jobs/${jobId}/devices?device=${lens.id}`);
  await expect(page.getByLabel('Focal length, shortest (mm)')).toBeVisible();
  await expect(page.getByLabel('Sensor width (mm)')).toHaveCount(0);
  await expect(page.getByLabel('Maximum useful distance (m)')).toHaveCount(0);
});
