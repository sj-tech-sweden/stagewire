import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

async function call(
  request: APIRequestContext,
  headers: Record<string, string>,
  method: 'post' | 'put',
  path: string,
  data: object,
) {
  const res = await request[method](`${API_BASE}/api/v1${path}`, { headers, data });
  expect(res.status(), `${path}: ${await res.text()}`).toBeLessThan(300);
  return res.json();
}

// Regression guard for NotesDisplay: notes are user-authored markdown. Script tags, inline event
// handlers and javascript: URLs must never reach the DOM, while the safe markdown around them
// still renders.
test('hostile markup in notes is neutralised and never executes', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await call(request, headers, 'post', '/jobs', { title: `Notes XSS ${Date.now()}` });
  const list = await call(request, headers, 'post', `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  const base = `/jobs/${job.id}/channel-lists/${list.id}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  await call(request, headers, 'post', `${base}/outputs`, {
    name: 'Wedge XSS',
    notes: [
      '**safe** text',
      '<img src="x" onerror="window.__xss = 1">',
      '<script>window.__xss = 2</script>',
      '[click](javascript:window.__xss = 3)',
      '<a href="javascript:window.__xss = 4">link</a>',
    ].join('\n\n'),
  });

  const dialogs: string[] = [];
  page.on('dialog', (d) => {
    dialogs.push(d.message());
    void d.dismiss();
  });

  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await page.getByTestId('console-tab-buses').click();
  const display = page.getByTestId('console-bus').first().getByTestId('notes-display');
  await expect(display.locator('strong', { hasText: 'safe' })).toBeVisible();

  await expect(display.locator('script')).toHaveCount(0);
  await expect(display.locator('[onerror]')).toHaveCount(0);
  await expect(display.locator('a[href^="javascript:" i]')).toHaveCount(0);
  await expect(display.locator('[href^="javascript:" i]')).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).__xss)).toBeUndefined();
  expect(dialogs).toEqual([]);
});
