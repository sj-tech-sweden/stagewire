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

test('the stage plot loads DMX and outlet data; the outlet toggle is remembered', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Stage Lights ${Date.now()}` })).id as string;
  const venue = await post(request, headers, '/venues', { name: `E2E Hall ${Date.now()}` });
  await post(request, headers, `/venues/${venue.id}/power-outlets`, { name: 'Wall SR', connector: 'schuko', x_cm: 100, y_cm: 80 });
  await request.put(`${API_BASE}/api/v1/jobs/${jobId}/venue`, { headers, data: { venue_id: venue.id } });
  const console = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Console', device_type: 'mixer' });
  await post(request, headers, `/jobs/${jobId}/fixtures`, { device_name: 'Stage Wash', universe: 1, dmx_address: 1, footprint: 8 });
  const devices = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json();
  const wash = devices.find((d: { name: string }) => d.name === 'Stage Wash');
  await post(request, headers, `/jobs/${jobId}/plot-elements`, { element_type: 'moving_light', label: 'Wash', linked_device_id: wash.id, position_x: 200, position_y: 100 });
  await post(request, headers, `/jobs/${jobId}/plot-elements`, { element_type: 'mixer', label: 'Desk', linked_device_id: console.id, position_x: 50, position_y: 300 });
  const universe = await post(request, headers, `/jobs/${jobId}/dmx-universes`, { number: 1, source_device_id: console.id });
  await post(request, headers, `/jobs/${jobId}/dmx-universes/${universe.id}/steps`, { fixture_id: (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/fixtures`, { headers })).json())[0].id });

  const universesLoaded = page.waitForResponse((r) => r.url().includes('/dmx-universes') && r.status() === 200);
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await universesLoaded;
  await expect(page.getByText('DMX cables', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Power outlets', { exact: true })).toBeVisible();

  await page.getByText('Power outlets', { exact: true }).click();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('sw_stage_outlets'))).toBe('false');
  await page.reload();
  await expect.poll(() => page.evaluate(() => localStorage.getItem('sw_stage_outlets'))).toBe('false');
});
