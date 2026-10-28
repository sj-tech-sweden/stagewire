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

test('a camera sensor width can be calculated or picked from a preset', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Sensor ${Date.now()}` })).id as string;
  const camera = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Cam Sensor', device_type: 'camera' });

  await page.goto(`/jobs/${jobId}/devices?device=${camera.id}`);
  await expect(page.getByLabel('Aspect ratio')).toBeVisible();
  await page.getByLabel('Aspect ratio').fill('3:2');
  await page.getByLabel('Diagonal').fill('43.27');
  await expect(page.getByText(/Width 36\.00 mm/)).toBeVisible();
  await page.getByRole('button', { name: 'Use this width' }).click();
  await expect(page.getByLabel('Sensor width (mm)')).toHaveValue('36');

  await page.getByRole('combobox', { name: 'Standard sensor' }).click();
  await page.getByRole('option', { name: /APS-C \(Sony, Nikon\)/ }).click();
  await expect(page.getByLabel('Sensor width (mm)')).toHaveValue('23.5');
  await expect(page.getByLabel('Aspect ratio')).toHaveValue('3:2');
});

test('a placed camera can create a new camera device from the stage plot', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Camera Link ${Date.now()}` })).id as string;

  const loaded = page.waitForResponse((res) => res.url().includes('/plot-elements') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.getByText('Camera', { exact: true }).first().click();
  await expect(page.getByRole('button', { name: 'Create new camera device' })).toBeVisible();
  await page.getByRole('button', { name: 'Create new camera device' }).click();

  await expect
    .poll(async () => {
      const devices = (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json()) as Array<{ device_type: string }>;
      return devices.filter((d) => d.device_type === 'camera').length;
    })
    .toBe(2);
  await expect
    .poll(async () => {
      const elements = (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, { headers })).json()) as Array<{ element_type: string; linked_device_id: string | null }>;
      const devices = (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json()) as Array<{ id: string; name: string }>;
      const linked = devices.find((d) => d.id === elements.find((e) => e.element_type === 'camera')?.linked_device_id);
      return linked?.name ?? null;
    })
    .toBe('Camera 2');
});
