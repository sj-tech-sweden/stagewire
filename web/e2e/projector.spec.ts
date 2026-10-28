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

test('a projector without a screen asks for one on the plot', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Projector ${Date.now()}` })).id as string;

  const loaded = page.waitForResponse((res) => res.url().includes('/plot-elements') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.getByText('Projector', { exact: true }).first().click();
  await expect(page.getByText(/Place a screen on the plot/)).toBeVisible();
});

test('a projector next to a screen asks for its throw ratio, and the screen can be placed', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Screen ${Date.now()}`, venue_width_cm: 1000, venue_height_cm: 800 })).id as string;
  await post(request, headers, `/jobs/${jobId}/plot-elements`, {
    element_type: 'screen',
    label: 'Screen',
    position_x: 300,
    position_y: 40,
    width_cm: 200,
    height_cm: 112,
    rotation: 0,
  });

  const loaded = page.waitForResponse((res) => res.url().includes('/plot-elements') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.getByText('Projector', { exact: true }).first().click();
  await expect(page.getByText(/Set the throw ratio on the projector/)).toBeVisible();
});
