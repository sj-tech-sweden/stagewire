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

async function listState(request: APIRequestContext, headers: Record<string, string>, jobId: string) {
  const res = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/video-lists`, { headers });
  return (await res.json())[0];
}

test('bulk add inputs and outputs, and choose the list switcher', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Video Bulk ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/video-lists`, { name: 'Cameras' });

  await page.goto(`/jobs/${jobId}?view=video`);
  await page.getByRole('button', { name: 'Bulk add inputs' }).click();
  await page.getByLabel('How many').fill('3');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect
    .poll(async () => (await listState(request, headers, jobId)).inputs.length)
    .toBe(3);

  await page.getByRole('button', { name: 'Bulk add outputs' }).click();
  await page.getByLabel('How many').fill('2');
  await page.getByLabel('Name prefix').fill('LED');
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect
    .poll(async () => (await listState(request, headers, jobId)).outputs.map((o: { name: string }) => o.name))
    .toEqual(['LED 1', 'LED 2']);

  await page.getByRole('button', { name: 'Pick switcher from Stockwire' }).click();
  await page.getByLabel('Inputs', { exact: true }).fill('6');
  await page.getByLabel('Outputs', { exact: true }).fill('2');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect
    .poll(async () => {
      const list = await listState(request, headers, jobId);
      return [list.switcher_inputs, list.switcher_outputs];
    })
    .toEqual([6, 2]);
});
