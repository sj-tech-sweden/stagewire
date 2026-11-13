import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

// "Another browser" here is a second API client: the server publishes the same realtime events no
// matter which client wrote, so what these specs prove is that an open workspace follows changes it
// did not make itself, without a refresh.

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
  data?: object,
) {
  const res = await request[method](`${API_BASE}/api/v1${path}`, { headers, data });
  expect(res.status(), `${path}: ${await res.text()}`).toBeLessThan(300);
  return res.json();
}

async function seed(request: APIRequestContext, headers: Record<string, string>) {
  const job = await call(request, headers, 'post', '/jobs', { title: `Realtime ${Date.now()}` });
  const list = await call(request, headers, 'post', `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  const channels = [];
  for (const n of [1, 2]) {
    channels.push(
      await call(request, headers, 'post', `/jobs/${job.id}/channel-lists/${list.id}/channels`, {
        channel_number: n,
        source_label: `Src ${n}`,
      }),
    );
  }
  const base = `/jobs/${job.id}/channel-lists/${list.id}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  return { jobId: job.id as string, base, channels };
}

// An event is only delivered to a socket that is connected when it is published, so a spec must
// wait for the job socket before another "browser" writes.
async function openWorkspace(page: Page, jobId: string) {
  // The job socket sends nothing until something changes, so "connected" is the socket's creation
  // plus a moment for the handshake; listen from before the page loads.
  const created = page.waitForEvent('websocket', (ws) => ws.url().includes(`/ws/jobs/${jobId}`));
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  await created;
  await page.waitForTimeout(800);
}

async function openConsole(page: Page, jobId: string) {
  await openWorkspace(page, jobId);
  await page.getByTestId('open-console').click();
  await expect(page.getByTestId('console-panel')).toBeVisible();
}

test('faders, DCAs and the soft patch changed elsewhere appear without a refresh', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, base, channels } = await seed(request, headers);
  await openConsole(page, jobId);

  // faders: the other browser takes over the layout; this one shows "Your layout" at once
  await page.getByTestId('console-tab-faders').click();
  await expect(page.getByTestId('console-fader-start')).toBeVisible();
  await call(request, headers, 'put', `${base}/fader-layout`, { layout: { '1:A:5': channels[0].id } });
  await expect(page.getByTestId('console-fader-custom')).toBeVisible();

  // DCAs: a rename elsewhere shows in the name field
  await page.getByTestId('console-tab-dca').click();
  await call(request, headers, 'put', `${base}/dcas`, { dcas: { '1': { name: 'Drums', members: [channels[0].id] } } });
  await expect(page.getByTestId('console-dca-name').first()).toHaveValue('Drums');

  // soft patch: a socket patched elsewhere shows on the strip
  const box = await call(request, headers, 'post', `/jobs/${jobId}/devices`, {
    name: 'AR2412',
    device_type: 'analog_stagebox',
    ports: [{ direction: 'in', connector: 'xlr3', count: 24 }],
  });
  await page.getByTestId('console-tab-patch').click();
  await call(request, headers, 'put', `/jobs/${jobId}/channels/${channels[0].id}/soft-patch`, {
    device_id: box.id,
    port_id: 'in-xlr3',
    socket: 7,
  });
  await expect(page.getByTestId('console-patch-overview')).toContainText('AR2412');
});

test('the job header and the undo state follow another browser', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await call(request, headers, 'post', '/jobs', { title: `Before ${Date.now()}` });
  await openWorkspace(page, job.id);
  await expect(page.getByTestId('history-controls')).toBeVisible();
  await expect(page.getByTestId('history-undo')).toBeDisabled(); // nothing has been changed yet

  // another browser renames the job and adds a list: the title and the undo button update
  const title = `After ${Date.now()}`;
  await call(request, headers, 'patch', `/jobs/${job.id}`, { title });
  // the job's title is in the workspace header (a plain span, not a heading)
  await expect(page.locator('span', { hasText: title }).first()).toBeVisible();
  await expect(page.getByTestId('history-undo')).toBeEnabled();
});
