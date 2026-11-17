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
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-buses').click();

  // The bus that is a destination reports the preset that feeds it (reverse mapping, derived from
  // the preset). The caption is rendered text, so we match on it directly.
  await expect(page.getByTestId('console-bus').filter({ hasText: 'Talkback: Stage' })).toHaveCount(1);

  // Exactly one bus is a talkback destination here, so only one card shows a talkback indicator.
  await expect(page.getByTestId('console-bus').filter({ hasText: 'Talkback:' })).toHaveCount(1);
});

// The destinations of a talkback preset are chosen from the same grid strip-picker used elsewhere,
// not a plain multi-select. Selecting a bus there (rather than the API) must persist and be reflected
// as a reverse mapping on that bus card.
test('talkback destinations are chosen from the grid strip picker', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await call(request, headers, 'post', '/jobs', { title: `Talkback picker E2E ${Date.now()}` });
  const list = await call(request, headers, 'post', `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  const base = `/jobs/${job.id}/channel-lists/${list.id}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  await call(request, headers, 'post', `${base}/outputs`, { name: 'Wedge', mode: 'mono' });

  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-buses').click();

  // Add a preset, name it, then pick its destination from the grid.
  await page.getByTestId('console-talkback-preset-add').click();
  const nameInput = page.getByTestId('console-talkback-preset-name').last();
  await expect(nameInput).toBeVisible();
  await nameInput.fill('Stage');
  await page.getByTestId('console-talkback-preset-destinations').getByTestId('strip-picker-open').click();
  const tile = page.getByTestId('strip-picker-tile').filter({ hasText: 'Wedge' }).first();
  await expect(tile).toBeVisible();
  await tile.click();
  await page.getByTestId('strip-picker-done').click();

  // The chosen bus reports the preset that feeds it (reverse mapping, derived from the preset).
  await expect(page.getByTestId('console-bus').filter({ hasText: 'Talkback: Stage' })).toHaveCount(1);
});

// Regression: naming a preset saves on blur, and choosing its destination right after must not undo
// the name. Each save sends the whole preset list, so the second save used to build on the stale list.
// The preset saves are held back so the second edit is always made while the first is in flight.
test('a talkback preset keeps its name when a destination is chosen while the name is still saving', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await call(request, headers, 'post', '/jobs', { title: `Talkback race E2E ${Date.now()}` });
  const list = await call(request, headers, 'post', `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  const base = `/jobs/${job.id}/channel-lists/${list.id}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  await call(request, headers, 'post', `${base}/outputs`, { name: 'Wedge', mode: 'mono' });

  await page.route(`**${base}`, async (route) => {
    if (route.request().method() === 'PATCH') await new Promise((resolve) => setTimeout(resolve, 800));
    await route.continue();
  });

  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-buses').click();
  await page.getByTestId('console-talkback-preset-add').click();
  const nameInput = page.getByTestId('console-talkback-preset-name').last();
  await nameInput.fill('Stage');
  await page.getByTestId('console-talkback-preset-destinations').getByTestId('strip-picker-open').click();
  await page.getByTestId('strip-picker-tile').filter({ hasText: 'Wedge' }).first().click();
  await page.getByTestId('strip-picker-done').click();

  await expect
    .poll(async () => {
      const lists = (await (await request.get(`${API_BASE}/api/v1/jobs/${job.id}/channel-lists`, { headers })).json()) as Array<{
        id: string;
        talkback_presets: Array<{ name: string; destinations: unknown[] }>;
      }>;
      const preset = lists.find((l) => l.id === list.id)?.talkback_presets?.[0];
      return { name: preset?.name, destinations: preset?.destinations?.length ?? 0 };
    }, { timeout: 15000 })
    .toEqual({ name: 'Stage', destinations: 1 });
});
