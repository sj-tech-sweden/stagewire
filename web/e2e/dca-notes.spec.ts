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

// The common NotesDisplay renders DCA notes as markdown (with a read-more toggle); editing keeps
// raw text in the input, matching the bus notes pattern added alongside it.
test('DCA notes render as markdown and can be edited back to raw text', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await call(request, headers, 'post', '/jobs', { title: `DCA notes E2E ${Date.now()}` });
  const list = await call(request, headers, 'post', `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  const base = `/jobs/${job.id}/channel-lists/${list.id}`;
  // A digital console so the DCA tab is populated (gld-80 has 16 DCAs).
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });

  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await page.getByTestId('open-console').click();
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-dca').click();

  const dcaEl = page.getByTestId('console-dca').first();

  // With no notes yet, editing is offered via an "add" affordance.
  await dcaEl.getByTestId('console-dca-edit-notes').click();
  const input = dcaEl.getByTestId('console-dca-notes');
  await expect(input).toBeVisible();
  await input.fill('**Cue:** mute between songs.');
  await input.blur();

  // The change is saved as raw text on the DCA config (server is the source of truth).
  await expect
    .poll(async () => {
      const lists = await (
        await request.get(`${API_BASE}/api/v1/jobs/${job.id}/channel-lists`, { headers })
      ).json();
      const dcaConfig = lists.find((l: { id: string }) => l.id === list.id)?.dca_config || {};
      return dcaConfig['1']?.notes;
    })
    .toBe('**Cue:** mute between songs.');

  // Once the console's list data refreshes, the display renders the markdown again.
  await expect.poll(async () => {
    const el = dcaEl.getByTestId('notes-display');
    return (await el.count()) > 0 && (await el.innerHTML()).includes('<strong>Cue:</strong>');
  }).toBe(true);
});
