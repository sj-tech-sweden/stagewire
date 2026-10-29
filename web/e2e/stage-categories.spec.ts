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

test('categories of the stage plot can be hidden, and the choice is remembered', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Categories ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/plot-elements`, {
    element_type: 'performer',
    label: 'Singer',
    position_x: 100,
    position_y: 100,
    width_cm: 60,
    height_cm: 60,
  });

  const loaded = page.waitForResponse((res) => res.url().includes('/plot-elements') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.waitForLoadState('networkidle');

  await page.getByRole('button', { name: 'Video', exact: true }).click();
  await expect
    .poll(() => page.evaluate((id) => localStorage.getItem(`sw_stage_categories_${id}`), jobId))
    .not.toContain('"video"');
  await expect
    .poll(() => page.evaluate((id) => localStorage.getItem(`sw_stage_categories_${id}`), jobId))
    .toContain('"stage"');

  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect
    .poll(() => page.evaluate((id) => localStorage.getItem(`sw_stage_categories_${id}`), jobId))
    .not.toContain('"video"');
});

test('the Lighting category is shown by default and can be hidden', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Lighting Cat ${Date.now()}` })).id as string;

  await page.goto(`/jobs/${jobId}/stage-plot`);
  await page.waitForLoadState('networkidle');

  const lighting = page.getByRole('button', { name: 'Lighting', exact: true });
  // New categories default to visible even for an old saved set that lacked them.
  await expect(lighting).toHaveAttribute('aria-pressed', 'true');

  await lighting.click();
  await expect(lighting).toHaveAttribute('aria-pressed', 'false');
  await expect
    .poll(() => page.evaluate((id) => localStorage.getItem(`sw_stage_categories_${id}`), jobId))
    .not.toContain('"light"');

  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('button', { name: 'Lighting', exact: true })).toHaveAttribute('aria-pressed', 'false');
});

test('a previously saved category set that lacks Lighting still shows Lighting by default', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Old Cat ${Date.now()}` })).id as string;

  // Simulate an old browser that saved categories before 'light' existed.
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await page.waitForLoadState('networkidle');
  await page.evaluate(
    (id) => localStorage.setItem(`sw_stage_categories_${id}`, JSON.stringify(['sound', 'video', 'stage', 'other'])),
    jobId,
  );
  await page.reload();
  await page.waitForLoadState('networkidle');

  await expect(page.getByRole('button', { name: 'Lighting', exact: true })).toHaveAttribute('aria-pressed', 'true');
});
