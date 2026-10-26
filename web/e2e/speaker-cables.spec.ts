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

test('a speaker gets a cable from the amp at the end of its output chain', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);

  const job = await post(request, headers, '/jobs', {
    title: `E2E Speaker Cables ${Date.now()}`,
    venue_width_cm: 1000,
    venue_height_cm: 800,
  });
  const jobId = job.id as string;

  const mixer = await post(request, headers, `/jobs/${jobId}/devices`, {
    name: 'FOH desk',
    device_type: 'mixer',
  });
  const stagebox = await post(request, headers, `/jobs/${jobId}/devices`, {
    name: 'Stagebox',
    device_type: 'digital_stagebox',
  });
  const amp = await post(request, headers, `/jobs/${jobId}/devices`, {
    name: 'Amp rack',
    device_type: 'amp',
  });

  const list = await post(request, headers, `/jobs/${jobId}/channel-lists`, { name: 'Outputs' });
  const output = await post(request, headers, `/jobs/${jobId}/channel-lists/${list.id}/outputs`, {
    name: 'Main L',
  });
  const base = `/jobs/${jobId}/channel-lists/${list.id}/outputs/${output.id}/points`;
  const p1 = await post(request, headers, base, { position: 0, device_id: mixer.id });
  const p2 = await post(request, headers, base, {
    position: 1,
    device_id: stagebox.id,
    parent_id: p1.id,
  });
  const p3 = await post(request, headers, base, { position: 2, device_id: amp.id, parent_id: p2.id });

  await post(request, headers, `/jobs/${jobId}/plot-elements`, {
    element_type: 'custom',
    label: 'Rack',
    position_x: 0,
    position_y: 200,
    width_cm: 40,
    height_cm: 40,
    linked_device_id: amp.id,
  });
  await post(request, headers, `/jobs/${jobId}/plot-elements`, {
    element_type: 'custom',
    label: 'Desk',
    position_x: 0,
    position_y: 500,
    width_cm: 80,
    height_cm: 40,
    linked_device_id: mixer.id,
  });
  await post(request, headers, `/jobs/${jobId}/plot-elements`, {
    element_type: 'speaker_main',
    label: 'Main L',
    position_x: 400,
    position_y: 200,
    width_cm: 42,
    height_cm: 72,
    linked_output_point_id: p3.id,
  });

  await page.goto(`/jobs/${jobId}/stage-plot`);
  await expect(page.getByText('Amp rack → Main L')).toBeVisible();
});
