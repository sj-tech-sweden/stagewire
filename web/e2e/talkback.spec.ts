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
  method: 'post' | 'put' | 'patch',
  path: string,
  data: object,
) {
  const res = await request[method](`${API_BASE}/api/v1${path}`, { headers, data });
  expect(res.status(), `${path}: ${await res.text()}`).toBeLessThan(300);
  return res.json();
}

// A bus shows, read-only, which talkback presets route to it. The presets are the source of truth
// (each lists its destinations); the bus card derives the reverse mapping and displays it.
test('a bus displays the talkback presets that feed it', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await call(request, headers, 'post', '/jobs', { title: `Talkback E2E ${Date.now()}` });
  const list = await call(request, headers, 'post', `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  const base = `/jobs/${job.id}/channel-lists/${list.id}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  const wedge = await call(request, headers, 'post', `${base}/outputs`, { name: 'Wedge', mode: 'mono' });

  // Define a talkback preset (via the list, as the editor would) that routes to the Wedge bus.
  await call(request, headers, 'patch', base, {
    talkback_presets: [{ name: 'Stage', destinations: [wedge.id] }],
  });

  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await page.getByTestId('open-console').click();
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-buses').click();

  // The bus that is a destination reports the preset that feeds it (reverse mapping, derived from
  // the preset). The caption is rendered text, so we match on it directly.
  await expect(page.getByTestId('console-bus').filter({ hasText: 'Talkback: Stage' })).toHaveCount(1);

  // Exactly one bus is a talkback destination here, so only one card shows a talkback indicator.
  await expect(page.getByTestId('console-bus').filter({ hasText: 'Talkback:' })).toHaveCount(1);
});
