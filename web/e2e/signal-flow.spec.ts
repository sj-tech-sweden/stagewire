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

test('the signal flow of an output opens without errors and lists its speaker', async ({ page, request }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (err) => pageErrors.push(err.message));

  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (
    await post(request, headers, '/jobs', { title: `E2E Signal Flow ${Date.now()}` })
  ).id as string;
  const mixer = await post(request, headers, `/jobs/${jobId}/devices`, {
    name: 'FOH desk',
    device_type: 'mixer',
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
  await post(request, headers, base, { position: 1, device_id: amp.id, parent_id: p1.id });

  await page.goto(`/jobs/${jobId}`);
  await page.getByText('Main L', { exact: true }).first().click();
  await page.getByRole('button', { name: 'Signal flow' }).first().click();

  await expect(page.getByText('Amp rack').first()).toBeVisible();
  expect(pageErrors).toEqual([]);
});
