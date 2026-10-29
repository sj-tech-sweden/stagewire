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

test('power cables load on the plot and the toggle is remembered', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Power Cables ${Date.now()}` })).id as string;
  const venue = await post(request, headers, '/venues', { name: `E2E Hall ${Date.now()}` });
  const outlet = await post(request, headers, `/venues/${venue.id}/power-outlets`, {
    name: 'Wall SR',
    connector: 'schuko',
    x_cm: 100,
    y_cm: 80,
  });
  await request.put(`${API_BASE}/api/v1/jobs/${jobId}/venue`, { headers, data: { venue_id: venue.id } });

  const dimmer = await post(request, headers, `/jobs/${jobId}/devices`, {
    name: 'Dimmer',
    device_type: 'fixture',
  });
  const wash = await post(request, headers, `/jobs/${jobId}/devices`, {
    name: 'Wash',
    device_type: 'fixture',
  });
  await post(request, headers, `/jobs/${jobId}/plot-elements`, {
    element_type: 'moving_light',
    label: 'Dimmer',
    linked_device_id: dimmer.id,
    position_x: 200,
    position_y: 100,
  });
  await post(request, headers, `/jobs/${jobId}/plot-elements`, {
    element_type: 'moving_light',
    label: 'Wash',
    linked_device_id: wash.id,
    position_x: 300,
    position_y: 100,
  });

  const source = await post(request, headers, `/jobs/${jobId}/power-nodes`, {
    name: 'Mains',
    kind: 'source',
    feed_connector: 'schuko',
    venue_outlet_id: outlet.id,
    outputs: [{ connector: 'schuko', count: 3 }],
    rating_amps: 16,
  });
  const distro = await post(request, headers, `/jobs/${jobId}/power-nodes`, {
    name: 'Distro',
    kind: 'distro',
    parent_id: source.id,
    feed_connector: 'schuko',
    device_id: dimmer.id,
    outputs: [{ connector: 'schuko', count: 3 }],
    rating_amps: 16,
  });
  await post(request, headers, `/jobs/${jobId}/power-nodes`, {
    name: 'Wash feed',
    kind: 'breakout',
    parent_id: distro.id,
    feed_connector: 'schuko',
    device_id: wash.id,
  });

  const loaded = page.waitForResponse((res) => res.url().includes('/power-nodes') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.waitForLoadState('networkidle');

  const toggle = page.getByText('Power cables', { exact: true });
  await expect(toggle).toBeVisible();

  await toggle.click();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('sw_stage_power_cables')))
    .toBe('false');

  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem('sw_stage_power_cables')))
    .toBe('false');
});
