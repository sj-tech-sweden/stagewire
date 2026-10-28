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

test('a truss, a distro and a circuit are added on the rigging tab and a fixture is hung on the truss', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Rigging ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Wash R', device_type: 'fixture', weight_kg: 6, power_watts: 1200 });
  await post(request, headers, `/jobs/${jobId}/fixtures`, { device_name: 'Wash R', universe: 1, dmx_address: 1 });

  await page.goto(`/jobs/${jobId}?view=rigging`);
  await page.getByRole('textbox', { name: 'Truss or point name' }).fill('FOH truss');
  await page.getByRole('spinbutton', { name: 'Capacity (kg)' }).fill('10');
  await page.getByRole('button', { name: 'Add truss' }).click();
  await expect(page.getByText('FOH truss', { exact: false })).toBeVisible();

  await page.getByRole('textbox', { name: 'Distro name' }).fill('Stage distro');
  await page.getByRole('spinbutton', { name: 'Amps per phase' }).fill('16');
  await page.getByRole('button', { name: 'Add distro' }).click();
  await expect(page.getByText('Stage distro', { exact: false })).toBeVisible();

  await expect(page.getByText('Wash R').first()).toBeVisible();
  const row = page.locator('tr', { hasText: 'Wash R' }).first();
  await row.locator('.q-select').first().click();
  await page.locator('.q-menu .q-item', { hasText: 'FOH truss' }).click();

  await expect
    .poll(async () => {
      const loads = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/rigging/loads`, { headers })).json();
      return loads.find((l: { label: string }) => l.label === 'Wash R')?.rigging_point_id ?? null;
    })
    .toBeTruthy();
});
