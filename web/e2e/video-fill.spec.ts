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

test('editing an input and setting a switcher fills the remaining inputs and outputs', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Video Fill ${Date.now()}` })).id as string;
  const list = await post(request, headers, `/jobs/${jobId}/video-lists`, { name: 'Cameras' });
  await post(request, headers, `/jobs/${jobId}/video-lists/${list.id}/inputs`, { source_label: 'Cam 1' });

  await page.goto(`/jobs/${jobId}?view=video`);
  await page.getByRole('button', { name: 'Edit input' }).first().click();
  await page.getByLabel('Source', { exact: true }).fill('Stage left');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect
    .poll(async () => {
      const lists = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/video-lists`, { headers })).json();
      return lists[0].inputs[0].source_label;
    })
    .toBe('Stage left');

  await page.getByRole('button', { name: 'Pick switcher from Stockwire' }).click();
  await page.getByLabel('Pick switcher from Stockwire').fill('ATEM Mini');
  await page.locator('.q-menu .q-item').first().click();
  await page.getByLabel('Inputs', { exact: true }).fill('4');
  await page.getByLabel('Outputs', { exact: true }).fill('2');
  await page.getByRole('button', { name: 'Save', exact: true }).click();

  await expect
    .poll(async () => {
      const lists = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/video-lists`, { headers })).json();
      return [lists[0].inputs.length, lists[0].outputs.length];
    })
    .toEqual([4, 2]);
});
