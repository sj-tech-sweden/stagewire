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

// A job with a short channel list, opened on the Inputs table at a normal desktop width. The stored
// layout is cleared once up front so each spec starts from the automatic layout.
async function open(page: Page, request: APIRequestContext, width = 1400) {
  await page.setViewportSize({ width, height: 900 });
  await login(page);
  await page.evaluate(() => {
    for (const key of Object.keys(localStorage)) if (key.startsWith('sw_channel_cols')) localStorage.removeItem(key);
  });
  const headers = await authedHeaders(page);
  const job = await post(request, headers, '/jobs', { title: `Columns ${Date.now()}` });
  const list = await post(request, headers, `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  for (const [n, label] of [[1, 'Kick'], [2, 'Snare'], [3, 'Lead vocal']] as const) {
    await post(request, headers, `/jobs/${job.id}/channel-lists/${list.id}/channels`, { channel_number: n, source_label: label });
  }
  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await expect(page.getByTestId('channel-table')).toBeVisible();
  return job.id as string;
}

const header = (page: Page, label: string) =>
  page.getByTestId('channel-table').locator('th').filter({ hasText: new RegExp(`^\\s*${label}\\s*$`) });
const widthOf = async (page: Page, label: string) => Math.round((await header(page, label).boundingBox())!.width);

test('the automatic layout gives Name room for a name, and the table fits its container', async ({ page, request }) => {
  await open(page, request, 2000); // wide enough for every column at its minimum
  expect(await widthOf(page, 'Name')).toBeGreaterThanOrEqual(150);
  // the compact columns stay compact instead of sharing the space equally
  expect(await widthOf(page, '#')).toBeLessThan(100);
  expect(await widthOf(page, '48V')).toBeLessThan(100);
  const input = page.getByTestId('channel-label').first();
  await expect(input).toHaveValue('Kick');
  // nothing makes the table scroll sideways when there is room
  const [scroll, client] = await page.getByTestId('channel-table').locator('.q-table__middle').first().evaluate((el) => [el.scrollWidth, el.clientWidth]);
  expect(scroll).toBeLessThanOrEqual(client + 2);
});

test('columns can be hidden and the choice is remembered after a reload', async ({ page, request }) => {
  await open(page, request);
  await expect(header(page, 'Notes')).toBeVisible();
  await page.getByTestId('channel-columns').click();
  // required columns cannot be switched off
  await expect(page.getByTestId('channel-col-toggle-name')).toBeDisabled();
  await page.getByTestId('channel-col-toggle-notes').click();
  await page.keyboard.press('Escape');
  await expect(header(page, 'Notes')).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId('channel-table')).toBeVisible();
  await expect(header(page, 'Notes')).toHaveCount(0);
  // the space it freed went to the others: Name is wider than before it was hidden
  expect(await widthOf(page, 'Name')).toBeGreaterThanOrEqual(150);
});

test('a column can be resized by dragging its handle, keeps the width after a reload, and resets', async ({ page, request }) => {
  await open(page, request);
  const before = await widthOf(page, 'Name');
  const handle = page.getByTestId('channel-col-resize-name');
  const box = (await handle.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 40, box.y + box.height / 2, { steps: 4 });
  await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2, { steps: 4 });
  await page.mouse.up();
  await expect.poll(() => widthOf(page, 'Name')).toBeGreaterThan(before + 60);
  const dragged = await widthOf(page, 'Name');
  await page.reload();
  await expect(page.getByTestId('channel-table')).toBeVisible();
  expect(Math.abs((await widthOf(page, 'Name')) - dragged)).toBeLessThanOrEqual(3);

  // keyboard: a focused handle moves in steps of 10px (40 with Shift)
  await page.getByTestId('channel-col-resize-name').focus();
  await page.keyboard.press('ArrowLeft');
  await expect.poll(() => widthOf(page, 'Name')).toBeLessThan(dragged - 5);

  // double click goes back to the automatic width; Reset layout also brings hidden columns back
  await page.getByTestId('channel-col-resize-name').dblclick();
  await expect.poll(() => widthOf(page, 'Name')).toBeLessThan(dragged - 40);
  await page.getByTestId('channel-columns').click();
  await page.getByTestId('channel-col-toggle-notes').click();
  await expect(header(page, 'Notes')).toHaveCount(0);
  await page.getByTestId('channel-columns-reset').click();
  await expect(header(page, 'Notes')).toBeVisible();
  expect(await widthOf(page, 'Name')).toBeGreaterThanOrEqual(150);
});

test('when the space is too small the table scrolls sideways instead of squeezing Name', async ({ page, request }) => {
  await open(page, request, 1100);
  expect(await widthOf(page, 'Name')).toBeGreaterThanOrEqual(150);
  const [scroll, client] = await page.getByTestId('channel-table').locator('.q-table__middle').first().evaluate((el) => [el.scrollWidth, el.clientWidth]);
  expect(scroll).toBeGreaterThan(client);
  await expect(page.getByTestId('channel-label').first()).toBeVisible();
});
