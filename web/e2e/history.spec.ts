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

async function channelCount(request: APIRequestContext, headers: Record<string, string>, jobId: string) {
  const lists = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json();
  return lists.flatMap((l: { channels: unknown[] }) => l.channels).length;
}

async function seed(page: Page, request: APIRequestContext) {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await post(request, headers, '/jobs', { title: `History E2E ${Date.now()}` });
  const list = await post(request, headers, `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  await post(request, headers, `/jobs/${job.id}/channel-lists/${list.id}/channels`, { channel_number: 1, source_label: 'Vox' });
  return { headers, jobId: job.id as string, listId: list.id as string };
}

test('undo and redo by button and by keyboard step through the changes', async ({ page, request }) => {
  const { headers, jobId, listId } = await seed(page, request);
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  await expect(page.getByTestId('history-controls')).toBeVisible();
  await expect(page.getByTestId('history-undo')).toBeEnabled();
  await expect(page.getByTestId('history-redo')).toBeDisabled();
  // a second channel is created through the API; the controls follow it
  await post(request, headers, `/jobs/${jobId}/channel-lists/${listId}/channels`, { channel_number: 2, source_label: 'Gtr' });
  await page.reload();
  expect(await channelCount(request, headers, jobId)).toBe(2);
  // the button undoes the newest step
  await page.getByTestId('history-undo').click();
  await expect.poll(() => channelCount(request, headers, jobId)).toBe(1);
  await expect(page.getByTestId('history-redo')).toBeEnabled();
  // Ctrl+Z undoes the next one (focus is not in a text field)
  await page.locator('body').click({ position: { x: 5, y: 5 } });
  await page.keyboard.press('Control+z');
  await expect.poll(() => channelCount(request, headers, jobId)).toBe(0);
  // Ctrl+Shift+Z and the Redo button bring them back
  await page.keyboard.press('Control+Shift+z');
  await expect.poll(() => channelCount(request, headers, jobId)).toBe(1);
  await page.getByTestId('history-redo').click();
  await expect.poll(() => channelCount(request, headers, jobId)).toBe(2);
  await expect(page.getByTestId('history-redo')).toBeDisabled();
});

test('the version drawer lists the steps and restores an earlier version', async ({ page, request }) => {
  const { headers, jobId, listId } = await seed(page, request);
  for (const n of [2, 3]) {
    await post(request, headers, `/jobs/${jobId}/channel-lists/${listId}/channels`, { channel_number: n, source_label: `Ch ${n}` });
  }
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  await page.getByTestId('history-open').click();
  const drawer = page.getByTestId('history-drawer');
  await expect(drawer).toBeVisible();
  // newest first, the newest is the current version, and "before all changes" is the last row
  await expect(drawer.getByTestId('history-entry').first()).toContainText('Create channel');
  await expect(drawer.getByTestId('history-current')).toHaveCount(1);
  await expect(drawer.getByTestId('history-entry-start')).toBeVisible();
  // going back to the version after the first channel was made removes the other two
  const entries = drawer.getByTestId('history-entry');
  await entries.nth(2).click(); // list, channel 1, channel 2, channel 3 (newest first): the 1st channel
  await page.getByTestId('history-restore-ok').click();
  await expect.poll(() => channelCount(request, headers, jobId)).toBe(1);
  // the undone steps stay in the list (dimmed) and can be redone
  await expect(page.getByTestId('history-redo')).toBeEnabled();
  // "Before all changes" goes back to the very start, and a click on the newest entry returns
  await drawer.getByTestId('history-entry-start').click();
  await page.getByTestId('history-restore-ok').click();
  await expect.poll(() => channelCount(request, headers, jobId)).toBe(0);
  await entries.first().click();
  await page.getByTestId('history-restore-ok').click();
  await expect.poll(() => channelCount(request, headers, jobId)).toBe(3);
});

test('step names in the history drawer are translated', async ({ page, request }) => {
  const { headers, jobId } = await seed(page, request);
  // The app takes its language from the signed-in user's stored preference (it overwrites any
  // localStorage value at startup), so set it on the account and put it back afterwards: the
  // other specs in this run share the account and expect English.
  const me = await (await request.get(`${API_BASE}/api/v1/auth/me`, { headers })).json();
  const setLanguage = (preferred_language: string) =>
    request.put(`${API_BASE}/api/v1/auth/users/${me.id}`, { headers, data: { preferred_language } });
  expect((await setLanguage('sv')).ok()).toBeTruthy();
  try {
    await page.goto(`/jobs/${jobId}/workspace?view=lists`);
    await page.getByTestId('history-open').click();
    const drawer = page.getByTestId('history-drawer');
    await expect(drawer).toContainText('Skapa kanal');
    await expect(drawer).not.toContainText('Create channel');
  } finally {
    await setLanguage('en');
    await page.evaluate(() => {
      for (const key of Object.keys(localStorage)) if (key.includes('locale')) localStorage.removeItem(key);
    });
  }
});
