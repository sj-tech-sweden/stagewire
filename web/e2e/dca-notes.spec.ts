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

// The common NotesDisplay renders DCA notes as markdown (with a read-more toggle). Editing opens the
// shared MarkdownEditorDialog; saving persists the notes through the normal DCA saver.
test('DCA notes render as markdown and can be edited via the markdown editor', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await call(request, headers, 'post', '/jobs', { title: `DCA notes E2E ${Date.now()}` });
  const list = await call(request, headers, 'post', `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  const base = `/jobs/${job.id}/channel-lists/${list.id}`;
  // A digital console so the DCA tab is populated (gld-80 has 16 DCAs).
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });

  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-dca').click();

  const dcaEl = page.getByTestId('console-dca').first();

  // With no notes yet, editing is offered via an "add" affordance.
  await dcaEl.getByTestId('console-dca-edit-notes').click();
  const editor = page.getByTestId('markdown-editor-input');
  await expect(editor).toBeVisible();
  await editor.fill('**Cue:** mute between songs.');
  await page.getByTestId('markdown-editor-save').click();

  // The change is saved on the DCA config (server is the source of truth). The list GET does not
  // expose dca_config, so we read it back from the console summary's `dcas`.
  await expect
    .poll(async () => {
      const summary = await (
        await request.get(`${API_BASE}/api/v1/jobs/${job.id}/channel-lists/${list.id}/console`, {
          headers,
        })
      ).json();
      return summary.dcas?.['1']?.notes;
    })
    .toBe('**Cue:** mute between songs.');

  // Once saved, the display renders the markdown.
  await expect.poll(async () => {
    const el = dcaEl.getByTestId('notes-display');
    return (await el.count()) > 0 && (await el.innerHTML()).includes('<strong>Cue:</strong>');
  }).toBe(true);
});
