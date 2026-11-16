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

// The common NotesDisplay renders bus notes as markdown (with a read-more toggle); editing keeps
// raw text in the input, matching the pattern used elsewhere (DeviceInspector, JobDetails, lists).
test('bus notes render as markdown and can be edited back to raw text', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await call(request, headers, 'post', '/jobs', { title: `Bus notes E2E ${Date.now()}` });
  const list = await call(request, headers, 'post', `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  const base = `/jobs/${job.id}/channel-lists/${list.id}`;
  // A digital console so the buses tab is fully populated.
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  // Create the bus with markdown notes directly (POST accepts notes).
  const bus = await call(request, headers, 'post', `${base}/outputs`, {
    name: 'Wedge 1',
    notes: '**Heads up:** patch to FOH.',
  });

  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await page.getByTestId('open-console').click();
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-buses').click();

  // Exactly one bus exists in this test; target it directly (the bus name lives in an input
  // value, not text content, so hasText would not match it).
  const busEl = page.getByTestId('console-bus').first();

  // Notes render markdown (bold -> <strong>), not raw text, via the common NotesDisplay.
  const display = busEl.getByTestId('notes-display');
  await expect(display).toBeVisible();
  const html = await display.innerHTML();
  expect(html).toContain('<strong>Heads up:</strong>');

  // Editing is offered as a raw-text input; the rendered markdown is hidden while editing.
  await busEl.getByTestId('console-bus-edit-notes').click();
  const input = busEl.getByTestId('console-bus-notes');
  await expect(input).toBeVisible();
  await expect(display).toHaveCount(0);
  await input.fill('**Updated:** new routing info');
  await input.blur();
  // The change is saved (server is the source of truth; the console reloads via its websocket).
  await expect
    .poll(async () => {
      const lists = await (await request.get(`${API_BASE}/api/v1/jobs/${job.id}/channel-lists`, { headers })).json();
      const out = (lists.find((l: { id: string }) => l.id === list.id)?.outputs || []).find(
        (o: { id: string }) => o.id === bus.id,
      );
      return out?.notes;
    })
    .toBe('**Updated:** new routing info');

  // And once the console's list data refreshes, the display renders the updated markdown again.
  await expect.poll(async () => {
    const el = busEl.getByTestId('notes-display');
    return (await el.count()) > 0 && (await el.innerHTML()).includes('<strong>Updated:</strong>');
  }).toBe(true);
});
