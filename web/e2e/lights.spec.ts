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

test('a fixture added on the lights page appears in the patch with its DMX address', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Lights ${Date.now()}` })).id as string;

  await page.goto(`/jobs/${jobId}?view=lights`);
  await page.getByRole('button', { name: 'Add fixture' }).click();
  await page.getByLabel('Device name').fill('Robin 9');
  await page.getByLabel('Universe').fill('2');
  await page.getByLabel('DMX address').fill('17');
  await page.getByLabel('Footprint (channels)').fill('18');
  await page.getByRole('button', { name: 'Save', exact: true }).click();

  await expect(page.getByRole('cell', { name: 'Robin 9' })).toBeVisible();
  await expect(page.getByRole('cell', { name: '17', exact: true })).toBeVisible();
});

test('a CSV patch sheet imports fixtures and creates their devices', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Lights CSV ${Date.now()}` })).id as string;

  await page.goto(`/jobs/${jobId}?view=lights`);
  await page.getByRole('button', { name: 'Import patch' }).click();
  await page.locator('.q-dialog input[type=file]').setInputFiles({
    name: 'patch.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from('Universe;Address;Fixture Type;Channel Mode;Footprint;Name\n1;1;MAC Aura;Mode 1;16;Aura E2E 1\n'),
  });
  await page.getByRole('button', { name: 'Import', exact: true }).click();

  await expect(page.getByRole('cell', { name: 'Aura E2E 1' })).toBeVisible();
  const devices = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json();
  expect(devices.find((d: { name: string }) => d.name === 'Aura E2E 1')?.device_type).toBe('fixture');
});

test('a fixture type and its mode are created from the fixture form, and the mode sets the footprint', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Lights Types ${Date.now()}` })).id as string;

  await page.goto(`/jobs/${jobId}?view=lights`);
  await page.getByRole('button', { name: 'Add fixture' }).click();
  await page.getByLabel('Fixture type').fill('Par 64 Test');
  await page.keyboard.press('Enter');
  await page.getByLabel('Footprint (channels)').fill('6');
  await page.getByLabel('Channel mode').fill('8 bit');
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: 'Save', exact: true }).click();

  await expect(page.getByRole('cell', { name: 'Par 64 Test' })).toBeVisible();
  await expect(page.getByRole('cell', { name: '8 bit' })).toBeVisible();
  const types = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/fixture-types`, { headers })).json();
  expect(types[0].modes.map((m: { name: string; footprint: number }) => [m.name, m.footprint])).toEqual([['8 bit', 6]]);
});
