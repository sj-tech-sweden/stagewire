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

test('a switcher shows its inputs from the patch list in the device editor', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Switcher IO ${Date.now()}` })).id as string;
  const switcher = await post(request, headers, `/jobs/${jobId}/devices`, {
    name: 'ATEM Switcher',
    device_type: 'switcher',
  });
  const list = await post(request, headers, `/jobs/${jobId}/video-lists`, { name: 'Cameras' });
  for (const label of ['Cam 1', 'Cam 2']) {
    const input = await post(request, headers, `/jobs/${jobId}/video-lists/${list.id}/inputs`, {
      source_label: label,
    });
    await post(request, headers, `/jobs/${jobId}/video-inputs/${input.id}/patch-points`, {
      position: 0,
      device_id: switcher.id,
    });
  }

  await page.goto(`/jobs/${jobId}/devices`);
  await page.getByRole('button', { name: 'Edit', exact: true }).first().click();
  await expect(page.getByText('From patch list: 2', { exact: true })).toBeVisible();
});
