import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

// Every data table shares one wrapper (AdaptiveTable): its own saved column layout per table and
// user, and a floating copy of the header while the table is scrolled past.

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

async function seed(page: Page, request: APIRequestContext, channels: number) {
  await login(page);
  await page.evaluate(() => {
    for (const key of Object.keys(localStorage)) if (key.startsWith('sw_table_') || key.startsWith('sw_channel_cols')) localStorage.removeItem(key);
  });
  const headers = await authedHeaders(page);
  const job = await post(request, headers, '/jobs', { title: `Adaptive ${Date.now()}` });
  const list = await post(request, headers, `/jobs/${job.id}/graph/lists`, { name: 'FOH' });
  await post(
    request,
    headers,
    `/jobs/${job.id}/graph/lists/${list.id}/channels/batch`,
    Array.from({ length: channels }, (_, i) => ({ channel_number: i + 1, source_label: `Ch ${i + 1}` })),
  );
  await post(request, headers, `/jobs/${job.id}/graph/audio-devices`, { name: 'Amp', device_type: 'other', power_watts: 500 });
  return job.id as string;
}

const th = (page: Page, table: string, label: RegExp) => page.getByTestId(table).locator('th').filter({ hasText: label });

test('another table has its own saved layout that does not touch the channel list', async ({ page, request }) => {
  await page.setViewportSize({ width: 1500, height: 900 });
  const jobId = await seed(page, request, 3);
  await page.goto(`/jobs/${jobId}/workspace`);
  // the gear list: hide its Notes column through its own chooser
  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();
  await expect(page.getByTestId('workspace-table')).toBeVisible();
  await expect(th(page, 'workspace-table', /^\s*notes\s*$/i)).toBeVisible();
  await page.getByTestId('gear-columns').click();
  await expect(page.getByTestId('gear-col-toggle-name')).toBeDisabled(); // the identifying column stays
  await page.getByTestId('gear-col-toggle-notes').click();
  await page.keyboard.press('Escape');
  await expect(th(page, 'workspace-table', /^\s*notes\s*$/i)).toHaveCount(0);

  // saved under the gear table's key (per user), not under the channel list's
  const keys = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith('sw_table_') || k.startsWith('sw_channel_cols')));
  expect(keys.some((k) => k.startsWith('sw_table_gear_v1_'))).toBe(true);
  expect(keys.some((k) => k.startsWith('sw_channel_cols'))).toBe(false);

  await page.reload();
  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();
  await expect(page.getByTestId('workspace-table')).toBeVisible();
  await expect(th(page, 'workspace-table', /^\s*notes\s*$/i)).toHaveCount(0);

  // the channel list still shows its Notes column
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();
  await expect(page.getByTestId('channel-table')).toBeVisible();
  await expect(th(page, 'channel-table', /^\s*notes\s*$/i)).toBeVisible();
});

test('a floating header follows a table scrolled past its header and goes away with the table', async ({ page, request }) => {
  await page.setViewportSize({ width: 1500, height: 520 });
  const jobId = await seed(page, request, 60);
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  const table = page.getByTestId('channel-table');
  await expect(table).toBeVisible();
  const floating = page.getByTestId('channel-floating-header');
  await expect(floating).toHaveCount(0); // the real header is in view
  // room to scroll past the table whatever the page's own height is
  await page.evaluate(() => {
    document.body.style.paddingBottom = '3000px';
  });
  const tableTop = async () => Math.round((await table.boundingBox())!.y);

  // scroll until the table's own header is above the app header
  await page.evaluate((by) => window.scrollBy(0, by), (await tableTop()) + 120);
  await expect(floating).toBeVisible();
  // it lines up with the real column: same left edge and width for Name
  const realName = th(page, 'channel-table', /^\s*name\s*$/i).first();
  const floatName = floating.locator('th').filter({ hasText: /^\s*name\s*$/i });
  const real = (await realName.boundingBox())!;
  const copy = (await floatName.boundingBox())!;
  expect(Math.abs(copy.x - real.x)).toBeLessThan(3);
  expect(Math.abs(copy.width - real.width)).toBeLessThan(3);
  // it sits under the app header, not at the very top of the window
  const appHeader = await page.locator('.q-header').first().boundingBox();
  expect(copy.y).toBeGreaterThanOrEqual((appHeader?.y ?? 0) + (appHeader?.height ?? 0) - 2);

  // resizing from the floating header works and is saved like resizing the real one
  const before = copy.width;
  const handle = page.getByTestId('channel-fcol-resize-name');
  const hb = (await handle.boundingBox())!;
  await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2);
  await page.mouse.down();
  await page.mouse.move(hb.x + hb.width / 2 + 40, hb.y + hb.height / 2, { steps: 4 });
  await page.mouse.move(hb.x + hb.width / 2 + 70, hb.y + hb.height / 2, { steps: 4 });
  await page.mouse.up();
  await expect.poll(async () => Math.round((await floatName.boundingBox())!.width)).toBeGreaterThan(before + 40);
  const stored = await page.evaluate(() => {
    const key = Object.keys(localStorage).find((k) => k.startsWith('sw_channel_cols_v1_'));
    return key ? JSON.parse(localStorage.getItem(key)!).widths : null;
  });
  expect(stored.name).toBeGreaterThan(before + 40);

  // scrolled beyond the whole table: nothing left to label
  await page.evaluate(() => window.scrollBy(0, 4000));
  await expect(floating).toHaveCount(0);
  // back at the top: the real header is shown again, no floating copy
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(floating).toHaveCount(0);
  await expect(realName).toBeVisible();
});

test('the floating header disappears when the table is hidden by switching view', async ({ page, request }) => {
  await page.setViewportSize({ width: 1500, height: 520 });
  const jobId = await seed(page, request, 60);
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  const table = page.getByTestId('channel-table');
  await expect(table).toBeVisible();
  await page.evaluate(() => {
    document.body.style.paddingBottom = '3000px';
  });
  await page.evaluate((by) => window.scrollBy(0, by), Math.round((await table.boundingBox())!.y) + 120);
  const floating = page.getByTestId('channel-floating-header');
  await expect(floating).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();
  await expect(table).toHaveCount(0);
  await expect(floating).toHaveCount(0);
});
