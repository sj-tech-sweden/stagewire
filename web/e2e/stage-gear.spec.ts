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

test('a mixer and a switcher can be placed on the stage plot linked to their devices', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Gear ${Date.now()}` })).id as string;
  const mixer = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'FOH desk', device_type: 'mixer' });
  const switcher = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'ATEM Mini', device_type: 'switcher' });

  const loaded = page.waitForResponse((res) => res.url().includes('/devices') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.waitForLoadState('networkidle');
  await page.getByText('Mixer', { exact: true }).first().click();
  await page.getByText('Switcher', { exact: true }).first().click();

  await expect
    .poll(async () => {
      const elements = (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, { headers })).json()) as Array<{ element_type: string; linked_device_id: string; label: string }>;
      return elements.map((e) => [e.element_type, e.linked_device_id, e.label]).sort();
    })
    .toEqual(
      [
        ['mixer', mixer.id, 'FOH desk'],
        ['switcher', switcher.id, 'ATEM Mini'],
      ].sort(),
    );
});
