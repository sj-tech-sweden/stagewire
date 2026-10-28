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

test('the power tree and the trusses are shown on the rigging tab', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Rigging ${Date.now()}` })).id as string;
  const source = await post(request, headers, `/jobs/${jobId}/power-nodes`, {
    name: 'Mains A',
    kind: 'source',
    feed_connector: 'cee63_3p',
    outputs: [{ connector: 'cee32_3p', count: 2 }],
  });
  await post(request, headers, `/jobs/${jobId}/power-nodes`, {
    name: 'Distro A',
    kind: 'distro',
    parent_id: source.id,
    feed_connector: 'cee32_3p',
    outputs: [{ connector: 'schuko', count: 4, phase: 'L1' }],
  });
  await post(request, headers, `/jobs/${jobId}/rigging-points`, { name: 'FOH truss', weight_capacity_kg: 10 });

  await page.goto(`/jobs/${jobId}?view=rigging`);
  await expect(page.getByText('Mains A', { exact: false }).first()).toBeVisible();
  await expect(page.getByText('Distro A', { exact: false }).first()).toBeVisible();

  await expect(page.getByText('FOH truss', { exact: false }).first()).toBeVisible();
});
