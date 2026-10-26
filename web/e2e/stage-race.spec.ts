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

test('a slow stage save does not undo a cableway preference change', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Race ${Date.now()}`, stage_width_cm: 1200, stage_height_cm: 700 })).id as string;
  const cl = await post(request, headers, `/jobs/${jobId}/channel-lists`, { name: 'Outputs' });
  const out = await post(request, headers, `/jobs/${jobId}/channel-lists/${cl.id}/outputs`, { name: 'Main L' });
  const amp = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Amp rack', device_type: 'amp' });
  const mixer = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'FOH desk', device_type: 'mixer' });
  const base = `/jobs/${jobId}/channel-lists/${cl.id}/outputs/${out.id}/points`;
  const p1 = await post(request, headers, base, { position: 0, device_id: mixer.id });
  await post(request, headers, base, { position: 1, device_id: amp.id, parent_id: p1.id });
  await post(request, headers, `/jobs/${jobId}/plot-elements`, { element_type: 'custom', label: 'Rack', position_x: 0, position_y: 300, width_cm: 0, height_cm: 0, linked_device_id: amp.id });
  await post(request, headers, `/jobs/${jobId}/plot-elements`, { element_type: 'custom', label: 'Desk', position_x: 1000, position_y: 300, width_cm: 0, height_cm: 0, linked_device_id: mixer.id });
  await request.patch(`${API_BASE}/api/v1/jobs/${jobId}`, {
    headers,
    data: { cable_plan: { cableways: [{ id: 'tray', points: [[0, 0], [1000, 0]] }], routes: {}, settings: {} } },
  });

  // Hold back the stage save so it lands after the cable change.
  // Let the stage save reach the server, but hold its response until after the cable change.
  await page.route(`**/api/v1/jobs/${jobId}`, async (route) => {
    if (route.request().method() === 'PATCH' && route.request().postData()?.includes('stage_x_cm')) {
      const response = await route.fetch();
      await new Promise((resolve) => setTimeout(resolve, 2500));
      await route.fulfill({ response });
      return;
    }
    await route.continue();
  });

  const loaded = page.waitForResponse((res) => res.url().includes('/plot-elements') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.waitForLoadState('networkidle');
  await expect(page.getByText('straight (no cableway)')).toHaveCount(1);

  await page.getByLabel('Stage X (cm)').fill('150');
  await page.getByLabel('Stage X (cm)').press('Tab');
  const cableSlider = page.locator('div', { hasText: /Cableway preference/ }).locator('.q-slider').last();
  await cableSlider.scrollIntoViewIfNeeded();
  const box = await cableSlider.boundingBox();
  await page.mouse.move(box!.x + box!.width * 0.4, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(box!.x + 1, box!.y + box!.height / 2, { steps: 6 });
  await page.mouse.up();

  await expect(page.getByText('straight (no cableway)')).toHaveCount(0);
  await page.waitForTimeout(4000);
  await expect(page.getByText('straight (no cableway)')).toHaveCount(0);
});
