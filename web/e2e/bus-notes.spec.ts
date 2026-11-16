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

// The common NotesDisplay renders bus notes as markdown (with a read-more toggle). Editing opens
// the shared MarkdownEditorDialog (side-by-side editor + live preview); saving persists the notes.
test('bus notes render as markdown and can be edited via the markdown editor', async ({ page, request }) => {
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

  // Editing opens the shared markdown editor; the rendered markdown stays in the row behind it.
  await busEl.getByTestId('console-bus-edit-notes').click();
  const editor = page.getByTestId('markdown-editor-input');
  await expect(editor).toBeVisible();
  await editor.fill('**Updated:** new routing info');
  await page.getByTestId('markdown-editor-save').click();

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

// The toolbar lets non-Markdown users apply formatting: clicking Bold wraps the selection in **.
test('toolbar inserts markdown around the selection', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await call(request, headers, 'post', '/jobs', { title: `Bus toolbar E2E ${Date.now()}` });
  const list = await call(request, headers, 'post', `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  const base = `/jobs/${job.id}/channel-lists/${list.id}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  const bus = await call(request, headers, 'post', `${base}/outputs`, { name: 'Wedge 1' });

  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-buses').click();

  const busEl = page.getByTestId('console-bus').first();
  await busEl.getByTestId('console-bus-edit-notes').click();

  const editor = page.getByTestId('markdown-editor-input');
  await expect(editor).toBeVisible();
  await editor.fill('Hello');
  await editor.press('Control+a');
  await page.getByTestId('markdown-toolbar-bold').click();
  await page.getByTestId('markdown-editor-save').click();

  await expect
    .poll(async () => {
      const lists = await (await request.get(`${API_BASE}/api/v1/jobs/${job.id}/channel-lists`, { headers })).json();
      const out = (lists.find((l: { id: string }) => l.id === list.id)?.outputs || []).find(
        (o: { id: string }) => o.id === bus.id,
      );
      return out?.notes;
    })
    .toBe('**Hello**');
});

// Inline styles (bold here) toggle off when clicked again, rather than stacking markers.
test('bold toolbar button toggles off on second click', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await call(request, headers, 'post', '/jobs', { title: `Bus bold toggle E2E ${Date.now()}` });
  const list = await call(request, headers, 'post', `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  const base = `/jobs/${job.id}/channel-lists/${list.id}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  const bus = await call(request, headers, 'post', `${base}/outputs`, { name: 'Wedge 1' });

  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-buses').click();

  const busEl = page.getByTestId('console-bus').first();
  await busEl.getByTestId('console-bus-edit-notes').click();
  const editor = page.getByTestId('markdown-editor-input');
  await expect(editor).toBeVisible();
  await editor.fill('Hello');
  await editor.press('Control+a');
  await page.getByTestId('markdown-toolbar-bold').click();
  await page.getByTestId('markdown-toolbar-bold').click();
  await page.getByTestId('markdown-editor-save').click();

  await expect
    .poll(async () => {
      const lists = await (await request.get(`${API_BASE}/api/v1/jobs/${job.id}/channel-lists`, { headers })).json();
      const out = (lists.find((l: { id: string }) => l.id === list.id)?.outputs || []).find(
        (o: { id: string }) => o.id === bus.id,
      );
      return out?.notes;
    })
    .toBe('Hello');
});

// Heading buttons behave like a radio group: H2 on plain text adds "## ", H2 again removes it, and
// clicking a different level converts rather than stacking hashes.
test('heading buttons toggle and convert levels', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await call(request, headers, 'post', '/jobs', { title: `Bus heading E2E ${Date.now()}` });
  const list = await call(request, headers, 'post', `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  const base = `/jobs/${job.id}/channel-lists/${list.id}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  const bus = await call(request, headers, 'post', `${base}/outputs`, { name: 'Wedge 1' });

  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-buses').click();

  const busEl = page.getByTestId('console-bus').first();
  await busEl.getByTestId('console-bus-edit-notes').click();
  const editor = page.getByTestId('markdown-editor-input');
  await expect(editor).toBeVisible();
  await editor.fill('Title');
  await editor.press('Control+a');

  await page.getByTestId('markdown-toolbar-heading-2').click();
  await page.getByTestId('markdown-toolbar-heading-2').click();
  await page.getByTestId('markdown-toolbar-heading-1').click();
  await page.getByTestId('markdown-editor-save').click();

  await expect
    .poll(async () => {
      const lists = await (await request.get(`${API_BASE}/api/v1/jobs/${job.id}/channel-lists`, { headers })).json();
      const out = (lists.find((l: { id: string }) => l.id === list.id)?.outputs || []).find(
        (o: { id: string }) => o.id === bus.id,
      );
      return out?.notes;
    })
    .toBe('# Title');
});
