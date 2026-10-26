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

test('a device can be created from the video patch list and the signal flow shows it', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Video Devices ${Date.now()}` })).id as string;
  const list = await post(request, headers, `/jobs/${jobId}/video-lists`, { name: 'Cameras' });
  await post(request, headers, `/jobs/${jobId}/video-lists/${list.id}/inputs`, { source_label: 'Cam 1 FOH' });

  const loaded = page.waitForResponse((res) => res.url().includes('/video-lists') && res.ok());
  await page.goto(`/jobs/${jobId}?view=video`);
  await loaded;
  const picker = page.getByPlaceholder('Pick a device').first();
  await picker.click();
  await picker.fill('Atem Mini');
  await picker.press('Enter');
  await page.getByRole('button', { name: 'Create device' }).click();

  await expect
    .poll(async () => {
      const devices = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json();
      return devices.map((d: { name: string }) => d.name);
    })
    .toContain('Atem Mini');

  await page.getByRole('button', { name: 'Signal flow' }).first().click();
  await expect(page.getByText('Atem Mini', { exact: true })).toBeVisible();
  await expect(page.getByText('Cam 1 FOH', { exact: true })).toBeVisible();
});

test('the back button from the stage plot returns to the video view', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Video Back ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/video-lists`, { name: 'Cameras Back Test' });

  await page.goto(`/jobs/${jobId}?view=video`);
  await expect(page.getByText('Cameras Back Test').first()).toBeVisible();
  await page.getByRole('button', { name: 'Stage plot', exact: true }).click();
  await expect(page).toHaveURL(/stage-plot/);
  await page.getByRole('button', { name: 'Back', exact: true }).click();
  await expect(page).toHaveURL(/view=video/);
  await expect(page.getByText('Cameras Back Test').first()).toBeVisible();
});
