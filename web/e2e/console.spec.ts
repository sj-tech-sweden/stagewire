import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, enableStockwire, setStockwireEnabled, login, API_BASE } from './helpers';

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

async function seed(request: APIRequestContext, headers: Record<string, string>) {
  const job = await call(request, headers, 'post', '/jobs', { title: `Console E2E ${Date.now()}` });
  const list = await call(request, headers, 'post', `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  for (const n of [1, 2]) {
    await call(request, headers, 'post', `/jobs/${job.id}/channel-lists/${list.id}/channels`, {
      channel_number: n,
      source_label: `Src ${n}`,
    });
  }
  return { jobId: job.id as string, listId: list.id as string };
}

async function openConsole(page: Page, jobId: string) {
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  await expect(page.getByTestId('console-panel')).toBeVisible();
}

test('a simple console shows no bus budget or fader map', async ({ page, request }) => {
  await login(page);
  const { jobId } = await seed(request, await authedHeaders(page));
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-profile').click();
  await expect(page.getByTestId('console-simple-note')).toBeVisible();
  await expect(page.getByTestId('console-tab-faders')).toHaveCount(0);
  await page.getByTestId('console-tab-buses').click();
  await expect(page.getByTestId('console-no-budget')).toBeVisible();
  await expect(page.getByTestId('console-budget')).toHaveCount(0);
});

test('a preset shows the bus budget, and an overflow can be added anyway', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  // a tiny pool so the overflow is easy to reach
  await call(request, headers, 'put', `/jobs/${jobId}/channel-lists/${listId}/console-profile`, {
    profile: { bus_pool: { total_slots: 1 } },
  });
  await call(request, headers, 'post', `/jobs/${jobId}/channel-lists/${listId}/outputs`, {
    name: 'Wedge 1',
  });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-buses').click();
  await expect(page.getByTestId('console-budget-text')).toContainText('1 / 1');

  await page.getByTestId('console-new-bus-name').fill('Wedge 2');
  await page.getByTestId('console-add-bus').click();
  await page.getByText('Bus pool exceeded').first().waitFor();
  await page.getByRole('button', { name: 'Add anyway' }).click();
  await expect(page.getByTestId('console-bus')).toHaveCount(2);
  await expect(page.getByTestId('console-budget-warning')).toBeVisible();
});

test('choosing a preset enables the budget and fader map', async ({ page, request }) => {
  await login(page);
  const { jobId } = await seed(request, await authedHeaders(page));
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-profile').click();
  // the preset list is fetched when the panel mounts; a select with no options does not open, so
  // retry opening it until the list has arrived
  const gld = page.getByRole('option', { name: /GLD-80/ });
  await expect(async () => {
    await page.getByTestId('console-preset').click();
    await expect(gld).toBeVisible({ timeout: 1500 });
  }).toPass({ timeout: 20_000 });
  await gld.click();
  await page.getByTestId('console-apply-preset').click();
  await expect(page.getByTestId('console-source')).toContainText('Preset');
  await page.getByTestId('console-tab-buses').click();
  await expect(page.getByTestId('console-budget-text')).toContainText('0 / 30');
  await page.getByTestId('console-tab-faders').click();
  await expect(page.getByTestId('console-fader-grid')).toBeVisible();
});

test('the Inputs-page Stereo toggle links a pair, the console tile shows it and can unlink', async ({
  page,
  request,
}) => {
  await login(page);
  const { jobId } = await seed(request, await authedHeaders(page));
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  // one concept: the Inputs toggle goes through the validated link endpoint
  await page.getByTestId('channel-stereo').first().click();
  await expect(page.getByTestId('stereo-side').first()).toBeVisible();
  await page.getByTestId('console-tab-links').click();
  // the tile grid is the whole UI: the pair is one linked tile that names its legs
  const tile = page.getByTestId('console-pair-tile').first();
  await expect(tile).toHaveAttribute('data-state', 'linked');
  await expect(tile.getByTestId('console-pair-names')).toContainText('L/R');
  // each leg is patched on its own: the soft patch tab shows both channels
  await page.getByTestId('console-tab-patch').click();
  await expect(page.getByTestId('console-patch-card')).toHaveCount(2);
  await page.getByTestId('console-tab-links').click();
  // tapping a linked tile unlinks it after a confirmation
  await tile.click();
  await page.getByRole('button', { name: /ok/i }).click();
  await expect(tile).toHaveAttribute('data-state', 'free');
});

test('a stereo tile shows the channel names, a free tile what linking would join', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  // seed() made Ch 1 and Ch 2 ("Src 1", "Src 2"); add two named channels
  await call(request, headers, 'post', `${base}/channels`, { channel_number: 3, source_label: 'Kick' });
  await call(request, headers, 'post', `${base}/channels`, { channel_number: 4, source_label: 'Snare' });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-links').click();
  const tiles = page.getByTestId('console-pair-tile');
  await expect(tiles.first().getByTestId('console-pair-names')).toContainText('Src 1 · Src 2');
  await expect(tiles.nth(1).getByTestId('console-pair-names')).toContainText('Kick · Snare');
  // linking names the primary "<base> L" and the server derives "<base> R": the tile then reads L/R
  await tiles.nth(1).click();
  await expect(tiles.nth(1)).toHaveAttribute('data-state', 'linked');
  await expect(tiles.nth(1).getByTestId('console-pair-names')).toContainText('L/R');
  // the old long list of strips is gone
  await expect(page.getByTestId('console-strip')).toHaveCount(0);
});

test('the soft patch grid shows number, name, routing and pairing; selection works on tiles', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  for (const [n, label] of [[3, 'Kick'], [4, 'Snare']]) {
    await call(request, headers, 'post', `${base}/channels`, { channel_number: n, source_label: label });
  }
  const box = await call(request, headers, 'post', `/jobs/${jobId}/devices`, {
    name: 'AR2412',
    device_type: 'analog_stagebox',
    ports: [{ direction: 'in', connector: 'xlr3', count: 24 }],
  });
  // Ch 3 is already patched to socket 5; Ch 1-2 are a linked pair
  await call(request, headers, 'put', `/jobs/${jobId}/channels/${(await channelIdByNumber(request, headers, base, 3))}/soft-patch`, {
    device_id: box.id,
    port_id: 'in-xlr3',
    socket: 5,
  });
  const first = await channelIdByNumber(request, headers, base, 1);
  await call(request, headers, 'post', `${base}/console/link`, { primary_channel_id: first });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-patch').click();
  // the grid is the default view
  const cards = page.getByTestId('console-patch-card');
  await expect(cards).toHaveCount(4);
  const kick = cards.nth(2);
  await expect(kick.getByTestId('console-tile-name')).toContainText('Kick');
  await expect(kick.getByTestId('console-tile-route')).toContainText('AR2412 · 5');
  await expect(kick).toHaveAttribute('data-patched', 'true');
  // an unpatched tile says so, and the linked pair carries L / R badges
  await expect(cards.nth(3)).toHaveAttribute('data-patched', 'false');
  await expect(cards.nth(3).getByTestId('console-tile-route')).toContainText('—');
  await expect(cards.nth(0).getByTestId('console-tile-pair')).toContainText('L');
  await expect(cards.nth(1).getByTestId('console-tile-pair')).toContainText('R');
  // click toggles the selection, shift-click selects the range between
  await cards.nth(2).click();
  await cards.nth(3).click({ modifiers: ['Shift'] });
  await expect(page.getByTestId('console-select-count')).toContainText('2');
  // the list view is still there and the choice is kept
  await page.getByTestId('console-overview-view').getByRole('button').nth(1).click();
  await expect(page.getByTestId('console-patch-check').first()).toBeVisible();
});

test('grid selection feeds the auto patch dialog with a dry-run preview', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId } = await seed(request, headers);
  await call(request, headers, 'post', `/jobs/${jobId}/devices`, {
    name: 'AR2412',
    device_type: 'analog_stagebox',
    ports: [{ direction: 'in', connector: 'xlr3', count: 24 }],
  });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-patch').click();
  await page.getByTestId('console-select-all').click();
  await expect(page.getByTestId('console-select-count')).toContainText('2');
  await page.getByTestId('console-select-auto').click();
  await expect(page.getByTestId('console-auto-dialog')).toBeVisible();
  await page.getByTestId('console-auto-preview').click();
  await expect(page.getByTestId('console-auto-plan')).toContainText('→');
});

async function channelIdByNumber(request: APIRequestContext, headers: Record<string, string>, base: string, n: number) {
  const lists = await (await request.get(`${API_BASE}/api/v1${base.replace(/\/channel-lists\/.*/, '')}/channel-lists`, { headers })).json();
  for (const lst of lists) for (const c of lst.channels) if (c.channel_number === n) return c.id as string;
  throw new Error(`no channel ${n}`);
}

test('the faders start as a starting point; the first edit stores the whole layout and Auto fill resets it', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-faders').click();
  // the starting point shows the default fill and follows the console (nothing stored yet)
  await expect(page.getByTestId('console-fader-start')).toBeVisible();
  const before = await (await request.get(`${API_BASE}/api/v1${base}/fader-map`, { headers })).json();
  expect(before.custom).toBe(false);
  // the first edit takes over: the WHOLE map is stored, not only the edited fader
  await page.getByTestId('console-fader-edit').click();
  await page.getByTestId('console-fader').nth(10).click();
  await page.getByTestId('console-fader-choice').first().click();
  await expect(page.getByTestId('console-save-status')).toHaveAttribute('data-status', 'saved');
  await expect(page.getByTestId('console-fader-custom')).toBeVisible();
  const stored = await (await request.get(`${API_BASE}/api/v1${base}/fader-map`, { headers })).json();
  expect(stored.custom).toBe(true);
  const placed = (map: { layers: { banks: { strips: { id: string | null }[] }[] }[] }) =>
    map.layers.flatMap((l) => l.banks.flatMap((b) => b.strips)).filter((c) => c.id).length;
  expect(placed(stored)).toBeGreaterThan(placed(before) - 1); // the starting point survived the edit
  // a channel added afterwards is NOT placed behind the engineer's back: it is unplaced
  await call(request, headers, 'post', `${base}/channels`, { channel_number: 3, source_label: 'New' });
  await page.reload();
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-faders').click();
  // two strips are unplaced: the new channel, and the DCA the first edit displaced from its fader
  await expect(page.getByTestId('console-fader-unplaced')).toContainText('2 unplaced');
  const manual = await (await request.get(`${API_BASE}/api/v1${base}/fader-map`, { headers })).json();
  expect(manual.unplaced).toBe(2);
  // "Place unplaced strips" puts them on the next free faders
  await page.getByTestId('console-fader-place-unplaced').click();
  await expect(page.getByTestId('console-fader-unplaced')).toHaveCount(0);
  // "Auto fill (start over)" replaces the layout with the default fill, after a confirmation
  await page.getByTestId('console-fader-autofill').click();
  // the confirmation only appears while a stored layout exists; if the map has not caught up yet
  // there is nothing to confirm, so click OK only when the dialog is there
  const ok = page.getByRole('button', { name: /^ok$/i });
  if (await ok.isVisible({ timeout: 3000 }).catch(() => false)) await ok.click();
  await expect(page.getByTestId('console-save-status')).toBeVisible();
  // Auto fill is a request that stores the default layout: wait for it rather than read once
  const faderMap = async () =>
    (await (await request.get(`${API_BASE}/api/v1${base}/fader-map`, { headers })).json()) as {
      custom: boolean;
      unplaced: number;
    };
  await expect.poll(async () => (await faderMap()).custom).toBe(true);
  expect((await faderMap()).unplaced).toBe(0);
});

test('the mixer proposal shows the list need and whether each console fits', async ({ page, request }) => {
  // the mixer (set-mixer) control is only offered while the Stockwire integration is enabled
  await enableStockwire(request);
  await login(page);
  const { jobId } = await seed(request, await authedHeaders(page));
  // The catalog is not available in CI, so the proposal endpoint is mocked with its real shape.
  await page.route('**/propose-mixer**', (route) =>
    route.fulfill({
      json: {
        need: { strips: 2, mixes: 1, bus_slots: 2, roles: ['aux'], stereo_pairs: 0 },
        candidates: [
          { product_id: '1', name: 'GLD-80', fits: true, simple: false, headroom: { strips: 46, bus_slots: 28 }, reasons: [], unknown: [] },
          { product_id: '2', name: 'Tiny', fits: false, simple: true, headroom: { strips: 0, bus_slots: -1 }, reasons: ['1 outputs, 2 mixes needed'], unknown: [] },
        ],
      },
    }),
  );
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  await page.getByTestId('set-mixer').click();
  await page.getByText(/suggest mixer/i).click();
  await expect(page.getByTestId('mixer-need')).toContainText('2 input strips');
  await expect(page.getByText('GLD-80')).toBeVisible();
  await expect(page.getByText('1 outputs, 2 mixes needed')).toBeVisible();
});

test('a DCA can be named and given members, and the fader map shows it by name', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  await call(request, headers, 'put', `/jobs/${jobId}/channel-lists/${listId}/console-profile`, {
    preset: 'gld-80',
  });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-dca').click();
  await expect(page.getByTestId('console-dca')).toHaveCount(16);
  await page.getByTestId('console-dca-name').first().fill('Vocals');
  // members are chosen in the strip picker dialog (search / range / kind chips), not a dropdown
  await page.getByTestId('console-dca-members').first().getByTestId('strip-picker-open').click();
  await page.getByTestId('strip-picker-tile').first().click();
  await page.getByTestId('strip-picker-done').click();
  await expect(page.getByTestId('console-dca').first()).toContainText('1 assigned');
  await expect(page.getByTestId('console-save-status')).toHaveAttribute('data-status', 'saved');
  const summary = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists/${listId}/console`, {
    headers,
  });
  const body = await summary.json();
  expect(body.dcas['1'].name).toBe('Vocals');
  expect(body.dcas['1'].members).toHaveLength(1);
  await page.getByTestId('console-tab-faders').click();
  await expect(page.getByTestId('console-fader-grid')).toContainText('Vocals');
});

test('the console has its built-in FX engines up front; setting one up stores only that one', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-fx').click();
  // 8 built-in engines exist before anything is set up; none of them can be added or deleted
  await expect(page.getByTestId('console-fx')).toHaveCount(8);
  await expect(page.getByTestId('console-fx-placeholder')).toHaveCount(8);
  await expect(page.getByTestId('console-fx-count')).toContainText('0 / 8');
  await expect(page.getByTestId('console-fx-add')).toHaveCount(0);
  await expect(page.getByTestId('console-fx-remove')).toHaveCount(0);
  await page.getByTestId('console-fx-name').first().fill('Plate');
  await page.getByTestId('console-fx-sends').first().getByTestId('strip-picker-open').click();
  await page.getByTestId('strip-picker-tile').first().click();
  await page.getByTestId('strip-picker-done').click();
  await expect(page.getByTestId('console-fx-count')).toContainText('1 / 8');
  await expect(page.getByTestId('console-save-status')).toHaveAttribute('data-status', 'saved');
  const body = await (await request.get(`${API_BASE}/api/v1${base}/console`, { headers })).json();
  expect(body.fx).toHaveLength(8);
  const plate = body.fx.find((e: { name: string }) => e.name === 'Plate');
  expect(plate.configured).toBe(true);
  expect(plate.sends).toHaveLength(1);
  expect(body.fx.filter((e: { configured: boolean }) => e.configured)).toHaveLength(1);
  // a set-up engine is on the faders by default (the unset built-in ones stay off them)
  await page.getByTestId('console-tab-faders').click(); // nothing to confirm: it saved as it changed
  await expect(page.getByTestId('console-fader-grid')).toContainText('Plate');
  await page.getByTestId('console-tab-fx').click();
  // a built-in engine is reset, not deleted
  await page.getByTestId('console-fx-reset').first().click();
  await expect(page.getByTestId('console-fx-count')).toContainText('0 / 8');
  await expect(page.getByTestId('console-fx-name').first()).toHaveValue('FX 1');
  await page.getByTestId('console-tab-faders').click();
  await expect(page.getByTestId('console-fader-grid')).not.toContainText('Plate');
});

test('a fader strip can be dragged from the tray onto a fader', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  await call(request, headers, 'put', `/jobs/${jobId}/channel-lists/${listId}/console-profile`, {
    preset: 'gld-80',
  });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-faders').click();
  await page.getByTestId('console-fader-edit').click();
  await expect(page.getByTestId('console-fader-tray')).toBeVisible();
  await page.getByTestId('console-fader-tray-strip').first().dragTo(page.getByTestId('console-fader').nth(7));
  // taking over stores the WHOLE layout: every placed fader is now the engineer's (pinned)
  await expect(page.getByTestId('console-fader-pin').first()).toBeVisible();
  await expect(page.getByTestId('console-save-status')).toHaveAttribute('data-status', 'saved');
  const stored = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists/${listId}/fader-map`, { headers })).json();
  expect(stored.custom).toBe(true);
});

test('the console Buses tab shows the bus-pool budget and a role per bus on a digital console', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  await call(request, headers, 'put', `/jobs/${jobId}/channel-lists/${listId}/console-profile`, {
    profile: { bus_pool: { total_slots: 4 } },
  });
  await call(request, headers, 'post', `/jobs/${jobId}/channel-lists/${listId}/outputs`, {
    name: 'IEM',
    mode: 'stereo',
  });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-buses').click();
  await expect(page.getByTestId('console-budget-text')).toContainText('2 / 4');
  await expect(page.getByTestId('console-bus-role')).toBeVisible();
});

test('the console Buses tab bulk-adds buses with a chosen role', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  await call(request, headers, 'put', `/jobs/${jobId}/channel-lists/${listId}/console-profile`, {
    profile: { bus_pool: { total_slots: 40, allowed_roles: ['aux', 'group', 'matrix', 'main', 'fx_send'] } },
  });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-buses').click();
  await page.getByTestId('console-bulk-buses').click();
  await page.getByTestId('list-bulk-count').fill('3');
  await page.getByTestId('list-bulk-prefix').fill('Aux');
  await page.getByTestId('list-bulk-create').click();
  await expect(page.getByTestId('console-bus')).toHaveCount(3);
});

test('the strip picker selects by range, search and kind, and a DCA can hold FX sends', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  for (let n = 3; n <= 24; n += 1) {
    await call(request, headers, 'post', `${base}/channels`, { channel_number: n, source_label: `Src ${n}` });
  }
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  await call(request, headers, 'put', `${base}/fx`, { fx: [{ id: 'plate', name: 'Plate', type: 'reverb', sends: [] }] });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-dca').click();
  await page.getByTestId('console-dca-members').first().getByTestId('strip-picker-open').click();
  const dialog = page.getByTestId('strip-picker-dialog');
  // a range selects input channels only
  await dialog.getByTestId('strip-picker-range').fill('1-8, 20');
  await dialog.getByTestId('strip-picker-range-apply').click();
  await expect(dialog.getByTestId('strip-picker-count')).toContainText('9 selected');
  // the kind chips and search reach FX returns and FX sends, which a DCA may hold
  await dialog.getByTestId('strip-picker-kind-fxsend').click();
  // 8 FX sends exist (the configured Plate plus 7 built-in); search narrows to the one wanted
  await expect(dialog.getByTestId('strip-picker-tile')).toHaveCount(8);
  await dialog.getByTestId('strip-picker-search').fill('Plate send');
  await expect(dialog.getByTestId('strip-picker-tile')).toHaveCount(1);
  await dialog.getByTestId('strip-picker-all').click();
  await expect(dialog.getByTestId('strip-picker-count')).toContainText('10 selected');
  await dialog.getByTestId('strip-picker-done').click();
  await expect(page.getByTestId('console-save-status')).toHaveAttribute('data-status', 'saved');
  const body = await (await request.get(`${API_BASE}/api/v1${base}/console`, { headers })).json();
  expect(body.dcas['1'].members).toContain('fxs-plate');
  expect(body.dcas['1'].members).toHaveLength(10);
});

test('the fader tray lists FX returns and FX sends next to inputs and mixes', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  await call(request, headers, 'put', `${base}/fx`, { fx: [{ id: 'plate', name: 'Plate', type: 'reverb', sends: [] }] });
  await call(request, headers, 'post', `${base}/outputs`, { name: 'Wedge 1' });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-faders').click();
  await page.getByTestId('console-fader-edit').click();
  const tray = page.getByTestId('console-fader-tray');
  await expect(tray).toContainText('Plate');
  await expect(tray).toContainText('Plate send');
  await expect(tray).toContainText('Wedge 1');
  await page.getByTestId('console-fader-tray-kind-fxsend').click();
  // the console's 8 built-in FX each have a send (Plate is one of them)
  await expect(page.getByTestId('console-fader-tray-strip')).toHaveCount(8);
});

test('auto patch previews a plan onto a Dante card and then applies it', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  for (let n = 3; n <= 8; n += 1) {
    await call(request, headers, 'post', `${base}/channels`, { channel_number: n, source_label: `Src ${n}` });
  }
  await call(request, headers, 'put', `${base}/console-profile`, {
    profile: { bus_pool: { total_slots: 20 }, expansion_ports: [{ protocol: 'dante', slots: 1, max_channels: 128 }] },
  });
  await call(request, headers, 'put', `${base}/expansion`, {
    installed: [{ protocol: 'dante', channels_in: 128, channels_out: 0 }],
  });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-patch').click();
  await expect(page.getByTestId('console-port-list')).toContainText('dante');
  // 128 sockets are one port with a paged grid, not 128 dropdown rows
  await page.getByTestId('console-port').first().click();
  await expect(page.getByTestId('console-socket-pager')).toBeVisible();
  await page.getByTestId('console-auto-patch').click();
  const dialog = page.getByTestId('console-auto-dialog');
  await dialog.getByTestId('console-auto-channels').getByTestId('strip-picker-open').click();
  await page.getByTestId('strip-picker-range').fill('1-8');
  await page.getByTestId('strip-picker-range-apply').click();
  await page.getByTestId('strip-picker-done').click();
  await dialog.getByTestId('console-auto-start').fill('17');
  await dialog.getByTestId('console-auto-preview').click();
  // The plan maps channels to starting sockets; assert on that locale-neutral mapping rather than
  // the translated sentence (the runner's browser locale decides the language).
  await expect(dialog.getByTestId('console-auto-plan')).toContainText('Ch 1 → 17');
  // a preview changes nothing
  let ch = await (await request.get(`${API_BASE}/api/v1${base}/channels`, { headers })).json();
  expect(ch.every((c: { dsp_source: unknown }) => !c.dsp_source)).toBe(true);
  await dialog.getByTestId('console-auto-apply').click();
  await expect(page.getByTestId('console-socket-17')).toContainText('Ch 1');
  ch = await (await request.get(`${API_BASE}/api/v1${base}/channels`, { headers })).json();
  expect(ch.find((c: { channel_number: number }) => c.channel_number === 8).dsp_source.socket).toBe(24);
});

test('an expansion card is fitted within the console limits and becomes sockets', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  await call(request, headers, 'put', `${base}/console-profile`, {
    profile: { bus_pool: { total_slots: 20 }, expansion_ports: [{ protocol: 'dante', slots: 1, max_channels: 64 }] },
  });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-profile').click();
  await expect(page.getByTestId('console-expansion-port')).toContainText('dante');
  await page.getByTestId('console-expansion-fit').click();
  await expect(page.getByTestId('console-expansion-card')).toContainText('128 sockets');
  await page.getByTestId('console-expansion-in').fill('32');
  await page.getByTestId('console-expansion-out').fill('32');
  await expect(page.getByTestId('console-save-status')).toHaveAttribute('data-status', 'saved');
  const got = await (await request.get(`${API_BASE}/api/v1${base}/expansion`, { headers })).json();
  expect(got.installed[0]).toMatchObject({ protocol: 'dante', channels_in: 32, channels_out: 32 });
  await page.getByTestId('console-tab-patch').click();
  await expect(page.getByTestId('console-port-list')).toContainText('32');
});

test('nothing needs saving: edits persist by themselves and there is one status indicator', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  await openConsole(page, jobId);
  const status = page.getByTestId('console-save-status');
  // no Save buttons, no per-tab chips, no unsaved bars anywhere
  await page.getByTestId('console-tab-dca').click();
  await expect(page.getByTestId('console-dca-save')).toHaveCount(0);
  await expect(page.getByTestId('save-mode-draft')).toHaveCount(0);
  await page.getByTestId('console-dca-name').first().fill('Drums');
  await expect(status).toHaveAttribute('data-status', 'saved');
  let body = await (await request.get(`${API_BASE}/api/v1${base}/console`, { headers })).json();
  expect(body.dcas['1'].name).toBe('Drums');
  // it survives a reload, and switching tabs straight after typing loses nothing
  await page.getByTestId('console-dca-name').first().fill('Drums 2');
  await page.getByTestId('console-tab-buses').click();
  await expect(status).toHaveAttribute('data-status', 'saved');
  await page.reload();
  await page.getByTestId('console-tab-dca').click();
  await expect(page.getByTestId('console-dca-name').first()).toHaveValue('Drums 2');
  // an FX engine set up in the FX tab is stored without a click, and a DCA can hold its send at once
  await page.getByTestId('console-tab-fx').click();
  await page.getByTestId('console-fx-name').first().fill('Plate');
  await page.getByTestId('console-tab-dca').click();
  await page.getByTestId('console-dca-members').first().getByTestId('strip-picker-open').click();
  const dialog = page.getByTestId('strip-picker-dialog');
  await dialog.getByTestId('strip-picker-kind-fxsend').click();
  await dialog.getByTestId('strip-picker-all').click();
  await dialog.getByTestId('strip-picker-done').click();
  await expect(status).toHaveAttribute('data-status', 'saved');
  body = await (await request.get(`${API_BASE}/api/v1${base}/console`, { headers })).json();
  expect(body.fx.find((e: { name: string }) => e.name === 'Plate')).toBeTruthy();
  expect(body.dcas['1'].members.some((m: string) => m.startsWith('fxs-'))).toBe(true);
});

test('built-in FX are hidden on the faders until added, one at a time or all at once', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-faders').click();
  await expect(page.getByTestId('console-hidden-fx')).toBeVisible();
  await expect(page.getByTestId('console-hidden-fx-strip')).toHaveCount(16); // 8 returns + 8 sends
  await expect(page.getByTestId('console-fader-grid')).not.toContainText('FX 1');
  await page.getByTestId('console-hidden-fx-strip').first().click();
  await expect(page.getByTestId('console-hidden-fx-strip')).toHaveCount(15);
  await expect(page.getByTestId('console-fader-grid')).toContainText('FX 1');
  await page.getByTestId('console-add-all-fx').click();
  await expect(page.getByTestId('console-hidden-fx')).toHaveCount(0);
  // the FX tab's "On faders" switch reflects it
  await page.getByTestId('console-tab-fx').click();
  await expect(page.getByTestId('console-fx-on-faders').first()).toBeVisible();
});

test('bus outputs and direct outs can be auto patched onto output sockets', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  const box = await call(request, headers, 'post', `/jobs/${jobId}/devices`, {
    name: 'AR2412',
    device_type: 'analog_stagebox',
    ports: [{ direction: 'out', connector: 'xlr3', count: 12 }],
  });
  for (const name of ['Mix 1', 'Mix 2', 'Mix 3']) {
    await call(request, headers, 'post', `${base}/outputs`, { name, mode: 'mono' });
  }
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-patch').click();
  await page.getByText('Bus outputs').click(); // the third mode of the toggle
  await expect(page.getByTestId('console-patch-overview')).toContainText('Mix 1');
  await page.getByTestId('console-select-all').click();
  await page.getByTestId('console-select-auto').click();
  await expect(page.getByTestId('console-auto-dialog')).toBeVisible();
  await page.getByTestId('console-auto-start').fill('4');
  await page.getByTestId('console-auto-preview').click();
  await expect(page.getByTestId('console-auto-plan')).toContainText('→');
  await page.getByTestId('console-auto-apply').click();
  // the apply is a request: poll until the buses carry their sockets
  type Bus = { out_socket: { socket: number; device_id: string } | null };
  const outputs = async (): Promise<Bus[]> =>
    ((await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json()) as Array<{ outputs: Bus[] }>)[0].outputs;
  await expect.poll(async () => (await outputs()).map((o) => o.out_socket?.socket ?? null)).toEqual([4, 5, 6]);
  expect((await outputs())[0].out_socket!.device_id).toBe(box.id);
  // direct outs share the same output sockets: the next free ones are skipped
  await page.getByText('Direct out').first().click();
  await page.getByTestId('console-select-all').click();
  await page.getByTestId('console-select-auto').click();
  await page.getByTestId('console-auto-start').fill('4');
  await page.getByTestId('console-auto-preview').click();
  await expect(page.getByTestId('console-auto-plan')).toContainText('7');
});

test('a soft-patched channel shows its socket in the signal flow, with analog hops before it', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  const ports = [{ direction: 'in', connector: 'xlr3', count: 24 }];
  const box = await call(request, headers, 'post', `/jobs/${jobId}/devices`, {
    name: 'AR2412', device_type: 'analog_stagebox', ports,
  });
  const snake = await call(request, headers, 'post', `/jobs/${jobId}/devices`, {
    name: 'Snake', device_type: 'analog_snake', ports,
  });
  const channels = (await (await request.get(`${API_BASE}/api/v1${base}/channels`, { headers })).json()) as Array<{ id: string }>;
  await call(request, headers, 'put', `/jobs/${jobId}/channels/${channels[0].id}/soft-patch`, {
    device_id: box.id, port_id: 'in-xlr3', socket: 5,
  });
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  // the flow: the stagebox with its real input socket, then the mixer strip at the end
  await page.getByTestId('show-flow').first().click();
  const flow = page.getByTestId('chain-flow');
  await expect(flow).toContainText('AR2412');
  await expect(flow).toContainText('in 5');
  await expect(flow).toContainText('Ch 1');
  await page.getByTestId('flow-edit-chain').click();
  // the soft-patched hop is locked last; a snake can be added in front of it
  await expect(page.getByTestId('chain-locked-badge')).toContainText('In 5');
  await page.getByTestId('chain-add-step').click();
  const steps = page.getByTestId('chain-step');
  await expect(steps).toHaveCount(2);
  await steps.first().getByTestId('chain-device').click();
  await page.getByRole('option', { name: 'Snake' }).click();
  await page.getByTestId('chain-save').click();
  // the server kept the stagebox last: snake first, stagebox (soft patch) at the strip end
  type Row = { id: string; patch_points: Array<{ device_id: string; position: number }>; dsp_source: { socket: number } };
  const mineNow = async () =>
    ((await (await request.get(`${API_BASE}/api/v1${base}/channels`, { headers })).json()) as Row[]).find((c) => c.id === channels[0].id)!;
  const orderNow = async () =>
    [...(await mineNow()).patch_points].sort((a, b) => a.position - b.position).map((p) => p.device_id);
  await expect.poll(orderNow).toEqual([snake.id, box.id]); // the save is a request: wait for it
  expect((await mineNow()).dsp_source.socket).toBe(5);
});

test('a device typed into Edit patch is created with that name when the chain is saved', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  const channels = (await (await request.get(`${API_BASE}/api/v1${base}/channels`, { headers })).json()) as Array<{ id: string }>;
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  await page.getByTestId('show-flow').first().click();
  await page.getByTestId('flow-edit-chain').click();
  await page.getByTestId('chain-add-step').click();
  const step = page.getByTestId('chain-step').first();
  await step.getByTestId('chain-device').click();
  await page.keyboard.type('Snake 16');
  // not a known device: the picker offers to create it
  await page.getByTestId('chain-device-create').click();
  // (the test id sits on the select's inner input, so the step itself is what shows the name)
  await expect(step).toContainText('Snake 16');
  // nothing is created until Save: cancelling would leave no device behind
  const before = (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json()) as Array<{ name: string }>;
  expect(before.some((d) => d.name === 'Snake 16')).toBe(false);
  await page.getByTestId('chain-save').click();
  await expect
    .poll(async () => {
      const devices = (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json()) as Array<{ name: string }>;
      return devices.filter((d) => d.name === 'Snake 16').length;
    })
    .toBe(1); // exactly one, even though Save is the only action
  const devices = (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json()) as Array<{ id: string; name: string; ports: Array<{ direction: string; count: number }> }>;
  const snake = devices.find((d) => d.name === 'Snake 16')!;
  expect(snake.ports.map((p) => p.direction).sort()).toEqual(['in', 'out']);
  // the device is created first and the chain saved right after it: wait for the chain too
  const chainDevices = async () => {
    const rows = (await (await request.get(`${API_BASE}/api/v1${base}/channels`, { headers })).json()) as Array<{
      id: string; patch_points: Array<{ device_id: string }>;
    }>;
    return rows.find((c) => c.id === channels[0].id)!.patch_points.map((p) => p.device_id);
  };
  await expect.poll(chainDevices).toEqual([snake.id]);
});

test('a bus flow starts at the console/bus, shows the stagebox after it, and Edit patch opens the chain', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  // The console and the bus are one node. The soft patch stores a root hop for the console followed
  // by the patched stagebox; the flow must not draw the console twice (once as source, once as a hop).
  await call(request, headers, 'post', `/jobs/${jobId}/graph/devices`, {
    name: 'GLD-80', domain: 'audio', kind: 'mixer',
    attributes: { sound_list_id: listId },
    ports: [{ id: 'dsnake-out', direction: 'out', signal: 'data', connector: 'dsnake' }],
  });
  const box = await call(request, headers, 'post', `/jobs/${jobId}/graph/devices`, {
    name: 'AR2412', domain: 'audio', kind: 'digital_stagebox',
    ports: [{ id: 'out-xlr3', direction: 'out', signal: 'audio', connector: 'xlr3', channels: 24 }],
  });
  const bus = await call(request, headers, 'post', `/jobs/${jobId}/channel-lists/${listId}/outputs`, {
    name: 'Speaker', mode: 'mono',
  });
  await call(request, headers, 'put', `/jobs/${jobId}/outputs/${bus.id}/soft-patch`, {
    device_id: box.id, port_id: 'out-xlr3', socket: 5,
  });

  await openConsole(page, jobId);
  await page.getByTestId('console-tab-buses').click();
  await page.getByTestId('console-bus-show-flow').first().click();
  const flow = page.getByTestId('chain-flow');
  const titles = flow.locator('.dmx-flow-node .dmx-flow-title');
  // The bus itself is the source, with the stagebox output hanging off it — no console node feeding in.
  // Nodes are collected children-first, so don't rely on DOM order; assert the set of titles instead.
  await expect(titles).toHaveCount(2);
  await expect(titles.filter({ hasText: 'Speaker' })).toHaveCount(1);
  await expect(titles.filter({ hasText: 'AR2412' })).toHaveCount(1);

  // "Edit patch" used to emit into the void for buses: it must open the chain dialog.
  await page.getByTestId('flow-edit-chain').click();
  await expect(page.getByTestId('chain-save')).toBeVisible();
  // The bus chain editor uses a bus-specific hint (the old one said "from the source to the console").
  await expect(page.getByText('from the bus to the devices it feeds')).toBeVisible();
});

test('a bus soft-patched to multiple outputs shows them parallel, not daisy-chained', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  await call(request, headers, 'post', `/jobs/${jobId}/graph/devices`, {
    name: 'GLD-80', domain: 'audio', kind: 'mixer',
    attributes: { sound_list_id: listId },
    ports: [{ id: 'dsnake-out', direction: 'out', signal: 'data', connector: 'dsnake' }],
  });
  const mkBox = (name: string) =>
    call(request, headers, 'post', `/jobs/${jobId}/graph/devices`, {
      name, domain: 'audio', kind: 'digital_stagebox',
      ports: [{ id: 'out-xlr3', direction: 'out', signal: 'audio', connector: 'xlr3', channels: 24 }],
    });
  const box1 = await mkBox('AR2412');
  const box2 = await mkBox('AB168');
  const bus = await call(request, headers, 'post', `/jobs/${jobId}/channel-lists/${listId}/outputs`, {
    name: 'Speaker', mode: 'mono',
  });
  // Two endpoints: both hang off the console hop, so they are parallel outputs of the bus.
  await call(request, headers, 'put', `/jobs/${jobId}/outputs/${bus.id}/soft-patch`, {
    endpoints: [
      { refs: [{ device_id: box1.id, port_id: 'out-xlr3', socket: 5 }] },
      { refs: [{ device_id: box2.id, port_id: 'out-xlr3', socket: 6 }] },
    ],
  });

  await openConsole(page, jobId);
  await page.getByTestId('console-tab-buses').click();
  await page.getByTestId('console-bus-show-flow').first().click();
  const flow = page.getByTestId('chain-flow');
  const nodes = await flow.locator('.dmx-flow-node').evaluateAll((els) =>
    els.map((el) => ({
      title: (el.querySelector('.dmx-flow-title') as HTMLElement)?.textContent?.trim() || '',
      left: (el as HTMLElement).style.left,
    })),
  );
  const source = nodes.find((n) => n.title === 'Speaker');
  const devices = nodes.filter((n) => n.title === 'AR2412' || n.title === 'AB168');
  expect(source).toBeDefined();
  expect(devices).toHaveLength(2);
  // Same `left` means the same tree depth: siblings of the source, i.e. parallel (a daisy-chain
  // would put the second box one column further right). The source is one column left of them.
  expect(devices[0].left).toBe(devices[1].left);
  expect(source!.left).not.toBe(devices[0].left);
});

test('a bus chain offers every soft-patch output as a parent for manual devices', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const mkBox = (name: string) =>
    call(request, headers, 'post', `/jobs/${jobId}/graph/devices`, {
      name,
      domain: 'audio',
      kind: 'digital_stagebox',
      ports: [{ id: 'out-xlr3', direction: 'out', signal: 'audio', connector: 'xlr3', channels: 4 }],
    });
  const mkSpk = (name: string) =>
    call(request, headers, 'post', `/jobs/${jobId}/graph/devices`, {
      name,
      domain: 'audio',
      kind: 'loudspeaker',
      ports: [{ id: 'in-xlr3', direction: 'in', signal: 'audio', connector: 'xlr3', channels: 1 }],
    });
  const stageA = await mkBox('Stage A');
  const stageB = await mkBox('Stage B');
  const spkA = await mkSpk('Speaker A');
  const spkB = await mkSpk('Speaker B');
  const bus = await call(request, headers, 'post', `/jobs/${jobId}/channel-lists/${listId}/outputs`, {
    name: 'Choir',
    mode: 'mono',
  });
  await call(request, headers, 'put', `/jobs/${jobId}/outputs/${bus.id}/soft-patch`, {
    endpoints: [
      { refs: [{ device_id: stageA.id, port_id: 'out-xlr3', socket: 1 }] },
      { refs: [{ device_id: stageB.id, port_id: 'out-xlr3', socket: 2 }] },
    ],
  });

  await openConsole(page, jobId);
  await page.getByTestId('console-tab-buses').click();
  await page.getByTestId('console-bus-show-flow').first().click();
  await page.getByTestId('flow-edit-chain').click();

  // The two locked soft-patch outputs come first; new devices append after them, so the "From step"
  // picker can list both outputs as parents (it only offers earlier steps).
  await page.getByTestId('chain-add-step').click();
  await page.getByTestId('chain-add-step').click();
  const steps = page.getByTestId('chain-step');
  await expect(steps).toHaveCount(4);
  const first = steps.nth(2);
  const second = steps.nth(3);
  await first.getByTestId('chain-device').click();
  await page.getByRole('option', { name: 'Speaker A', exact: true }).click();
  await second.getByTestId('chain-device').click();
  await page.getByRole('option', { name: 'Speaker B', exact: true }).click();

  // Both outputs are offered, and an explicit choice is saved as that step's parent.
  await first.getByTestId('chain-from-step').click();
  await expect(page.getByRole('option', { name: 'From step 1', exact: true })).toBeVisible();
  await expect(page.getByRole('option', { name: 'From step 2', exact: true })).toBeVisible();
  await page.getByRole('option', { name: 'From step 2', exact: true }).click();
  await second.getByTestId('chain-from-step').click();
  await page.getByRole('option', { name: 'From step 1', exact: true }).click();
  await page.getByTestId('chain-save').click();

  // Reopen and confirm the two devices kept distinct, explicit parents (crossed on purpose).
  await page.getByTestId('console-bus-edit-chain').first().click();
  const saved = page.getByTestId('chain-step');
  await expect(saved.nth(2).getByTestId('chain-from-step')).toHaveValue('From step 2');
  await expect(saved.nth(3).getByTestId('chain-from-step')).toHaveValue('From step 1');
});

async function seedStageboxWithOutputs(request: APIRequestContext, headers: Record<string, string>, jobId: string) {
  return call(request, headers, 'post', `/jobs/${jobId}/devices`, {
    name: 'AR2412',
    device_type: 'analog_stagebox',
    ports: [
      { direction: 'in', connector: 'xlr3', count: 24 },
      { direction: 'out', connector: 'xlr3', count: 12 },
    ],
  });
}

test('a stereo bus is patched onto an adjacent pair and gets a second endpoint', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  await seedStageboxWithOutputs(request, headers, jobId);
  const bus = await call(request, headers, 'post', `${base}/outputs`, { name: 'IEM', mode: 'stereo' });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-patch').click();
  await page.getByTestId('console-patch-mode').getByText(/bus outputs/i).click();
  await page.getByTestId('console-port').filter({ hasText: 'out-xlr3' }).click();
  await page.getByTestId('console-patch-channel').click();
  await page.getByRole('option', { name: /IEM/ }).click();
  // one tap claims the pair 3-4 (L and R)
  await page.getByTestId('console-socket-3').click();
  await expect(page.getByTestId('console-bus-endpoint')).toContainText('3–4');
  await expect(page.getByTestId('console-socket-4')).toContainText('Mix');
  // a second endpoint (add mode): the main also goes to 7-8
  await page.getByTestId('console-add-endpoint').click();
  await page.getByTestId('console-socket-7').click();
  await expect(page.getByTestId('console-bus-endpoint')).toHaveCount(2);
  const buses = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json();
  const out = buses[0].outputs.find((o: { id: string }) => o.id === bus.id);
  expect(out.out_endpoints.map((e: { refs: { socket: number }[] }) => e.refs.map((r) => r.socket))).toEqual([[3, 4], [7, 8]]);
  // removing one endpoint leaves the other
  await page.getByTestId('console-bus-endpoint').first().getByRole('button').last().click();
  await expect(page.getByTestId('console-bus-endpoint')).toHaveCount(1);
});

test('a stereo bus can be routed to just its left or right, and the grid shows who is routed', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  await seedStageboxWithOutputs(request, headers, jobId);
  const bus = await call(request, headers, 'post', `${base}/outputs`, { name: 'IEM', mode: 'stereo' });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-patch').click();
  await page.getByTestId('console-patch-mode').getByText(/bus outputs/i).click();
  await page.getByTestId('console-port').filter({ hasText: 'out-xlr3' }).click();
  await page.getByTestId('console-patch-channel').click();
  await page.getByRole('option', { name: /IEM/ }).click();
  // left only: one socket, and the neighbour stays free
  await page.getByTestId('console-bus-side').getByText(/^left$/i).click();
  await page.getByTestId('console-socket-3').click();
  await expect(page.getByTestId('console-bus-endpoint')).toContainText('(L)');
  await expect(page.getByTestId('console-socket-3').getByTestId('console-socket-name')).toHaveText('IEM L');
  await expect(page.getByTestId('console-socket-4').getByTestId('console-socket-name')).toHaveCount(0);
  // the right goes to another socket without wiping the left
  await page.getByTestId('console-bus-side').getByText(/^right$/i).click();
  await page.getByTestId('console-socket-7').click();
  await expect(page.getByTestId('console-bus-endpoint')).toHaveCount(2);
  await expect(page.getByTestId('console-socket-7').getByTestId('console-socket-name')).toHaveText('IEM R');
  const lists = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json();
  const out = lists[0].outputs.find((o: { id: string }) => o.id === bus.id);
  expect(out.out_endpoints.map((e: { side: string; refs: { socket: number }[] }) => [e.side, e.refs[0].socket])).toEqual([['L', 3], ['R', 7]]);
});

test('an LCR bus can be patched one side at a time, centre included', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  await seedStageboxWithOutputs(request, headers, jobId);
  const bus = await call(request, headers, 'post', `${base}/outputs`, { name: 'PA', mode: 'lcr' });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-patch').click();
  await page.getByTestId('console-patch-mode').getByText(/bus outputs/i).click();
  await page.getByTestId('console-port').filter({ hasText: 'out-xlr3' }).click();
  await page.getByTestId('console-patch-channel').click();
  await page.getByRole('option', { name: /PA/ }).click();
  // each step waits for the toggle to show the side and for the endpoint to land before the next
  // one: the side is read when the socket is tapped, and taps during a refresh are dropped
  const side = page.getByTestId('console-bus-side');
  // an LCR bus routes all three by default, so its first option is "All", not "Both"
  await expect(side.getByRole('button', { name: /^all$/i })).toBeVisible();
  await expect(side.getByRole('button', { name: /^both$/i })).toHaveCount(0);
  let landed = 0;
  for (const [label, socket] of [['left', 1], ['right', 2], ['center', 9]] as const) {
    const button = side.getByRole('button', { name: new RegExp(`^${label}$`, 'i') });
    await button.click();
    await expect(button).toHaveAttribute('aria-pressed', 'true');
    await page.getByTestId(`console-socket-${socket}`).click();
    landed += 1;
    await expect(page.getByTestId('console-bus-endpoint')).toHaveCount(landed);
  }
  await expect(page.getByTestId('console-socket-9').getByTestId('console-socket-name')).toHaveText('PA C');
  const lists = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json();
  const out = lists[0].outputs.find((o: { id: string }) => o.id === bus.id);
  expect(out.out_endpoints.map((e: { side: string; refs: { socket: number }[] }) => [e.side, e.refs[0].socket])).toEqual([['L', 1], ['R', 2], ['C', 9]]);
});

test('patching a socket another channel already uses is allowed and shows the split-source hint', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  const box = await seedStageboxWithOutputs(request, headers, jobId);
  const ref = { device_id: box.id, port_id: 'in-xlr3', socket: 5 };
  const chans = await (await request.get(`${API_BASE}/api/v1${base}/channels`, { headers })).json();
  await call(request, headers, 'put', `/jobs/${jobId}/channels/${chans[0].id}/soft-patch`, ref);
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-patch').click();
  await page.getByTestId('console-port').filter({ hasText: 'in-xlr3' }).first().click();
  await page.getByTestId('console-patch-channel').click();
  await page.getByRole('option', { name: /Ch 2/ }).click();
  await page.getByTestId('console-socket-5').click();
  // not an error: a hint names the other channel and the socket is marked as shared
  await expect(page.getByText(/also takes this socket/i)).toBeVisible();
  await expect(page.getByTestId('console-socket-shared')).toBeVisible();
  const after = await (await request.get(`${API_BASE}/api/v1${base}/channels`, { headers })).json();
  expect(after.map((c: { dsp_source: { socket: number } | null }) => c.dsp_source?.socket)).toEqual([5, 5]);
});

test('the DCA member picker offers a grid of strips and selects a shift-range of tiles', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  const base = `/jobs/${jobId}/channel-lists/${listId}`;
  for (let n = 3; n <= 16; n += 1) {
    await call(request, headers, 'post', `${base}/channels`, { channel_number: n, source_label: `Src ${n}` });
  }
  await call(request, headers, 'put', `${base}/console-profile`, { preset: 'gld-80' });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-dca').click();
  await page.getByTestId('console-dca-members').first().getByTestId('strip-picker-open').click();
  const dialog = page.getByTestId('strip-picker-dialog');
  await expect(dialog.getByTestId('strip-picker-grid')).toBeVisible();
  const tiles = dialog.getByTestId('strip-picker-tile');
  await tiles.nth(1).click();
  await tiles.nth(4).click({ modifiers: ['Shift'] });
  await expect(dialog.getByTestId('strip-picker-count')).toContainText('4 selected');
  // the list view is still there, and the choice is remembered
  await dialog.getByTestId('strip-picker-view').getByRole('button').last().click();
  await expect(dialog.getByTestId('strip-picker-row').first()).toBeVisible();
  await dialog.getByTestId('strip-picker-done').click();
  await expect.poll(async () => {
    const body = await (await request.get(`${API_BASE}/api/v1${base}/console`, { headers })).json();
    return body.dcas['1']?.members?.length || 0;
  }).toBe(4);
});

test('a pair linked from the console tab shows on the Inputs page, and the Inputs toggle shows on the tab', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers); // channels 1 and 2
  await call(request, headers, 'put', `/jobs/${jobId}/channel-lists/${listId}/console-profile`, {
    preset: 'gld-80',
  });
  for (const n of [3, 4]) {
    await call(request, headers, 'post', `/jobs/${jobId}/channel-lists/${listId}/channels`, {
      channel_number: n,
      source_label: `Src ${n}`,
    });
  }
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  await page.getByTestId('console-tab-links').click();
  // link 1-2 from the console tab: the tile turns linked and the Inputs page shows the L/R badges
  const tile = page.getByTestId('console-pair-tile').first();
  await expect(tile).toHaveAttribute('data-state', 'free');
  await tile.click();
  await expect(tile).toHaveAttribute('data-state', 'linked');
  // the Inputs tab is where the L/R badges render; switch to it to see them
  await page.getByTestId('console-tab-inputs').click();
  await expect(page.getByTestId('stereo-side').first()).toBeVisible();
  // link 3-4 from the Inputs page: the console tile follows without a reload
  await page.getByTestId('channel-stereo').nth(2).click();
  await page.getByTestId('console-tab-links').click();
  await expect(page.getByTestId('console-pair-tile').nth(1)).toHaveAttribute('data-state', 'linked');
  // a range unlinks both, and the Inputs page loses its badges
  await page.getByTestId('console-pair-range').fill('1-4');
  await page.getByTestId('console-pair-unlink-range').click();
  await page.getByRole('button', { name: /ok/i }).click();
  await expect(page.getByTestId('console-pair-tile').first()).toHaveAttribute('data-state', 'free');
  await page.getByTestId('console-tab-inputs').click();
  await expect(page.getByTestId('stereo-side')).toHaveCount(0);
  // and a range links every free pair in it
  await page.getByTestId('console-tab-links').click();
  await page.getByTestId('console-pair-link-range').click();
  await expect(page.getByTestId('console-pair-tile').nth(1)).toHaveAttribute('data-state', 'linked');
});

test('the same channel can sit on two faders and the cells show x2', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId } = await seed(request, headers);
  await call(request, headers, 'put', `/jobs/${jobId}/channel-lists/${listId}/console-profile`, {
    preset: 'gld-80',
  });
  await openConsole(page, jobId);
  await page.getByTestId('console-tab-faders').click();
  await page.getByTestId('console-fader-edit').click();
  // the first fader holds Ch 1 (auto); open another fader and pick Ch 1 again
  await page.getByTestId('console-fader').nth(5).click();
  await page.getByTestId('console-fader-choice').first().click();
  await expect(page.getByTestId('console-fader-dup')).toHaveCount(2);
  await expect(page.getByTestId('console-save-status')).toHaveAttribute('data-status', 'saved');
  const map = await (
    await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists/${listId}/fader-map`, { headers })
  ).json();
  const strip = map.strips.find((s: { id: string }) => s.id === map.layers[0].banks[0].strips[0].id);
  expect(strip.placements).toBe(2);
  // "remove from this fader" takes one of them away again
  await page.getByTestId('console-fader').nth(5).click();
  await page.getByTestId('console-fader-remove').click();
  await expect(page.getByTestId('console-fader-dup')).toHaveCount(0);
});

test('source and stand selectors are usable when the Stockwire integration is disabled', async ({ page, request }) => {
  // The catalog picker only shows with the integration on; with it off the selectors must still render
  // and let you pick an existing job device (the unassigned audio devices) or type a new name.
  await setStockwireEnabled(request, false);
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId } = await seed(request, headers);
  // an audio device already in the job: picking it should link it as the channel source
  await call(request, headers, 'post', `/jobs/${jobId}/graph/audio-devices`, {
    name: 'Shure SM58',
    device_type: 'microphone',
  });
  await openConsole(page, jobId);
  const source = page.getByTestId('source-picker').first();
  const stand = page.getByTestId('stand-picker').first();
  await expect(source).toBeVisible();
  await expect(stand).toBeVisible();

  // pick an existing unassigned audio device from the job
  await source.click();
  await page.keyboard.type('SM58');
  await page.locator('.q-menu .q-item:not(.text-primary)', { hasText: 'Shure SM58' }).click();
  await expect
    .poll(async () =>
      ((await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json()) as any[])[0]
        ?.channels[0],
    )
    .toMatchObject({ device: 'Shure SM58' });

  // a typed name is stored as a new source device (the free-text option is the primary-coloured one).
  // Scope the option by the typed text: both the source and stand pickers render a "use as typed"
  // row, and a closed picker's row lingers in the DOM, so an un-scoped `.text-primary` can hit the
  // wrong one.
  await source.click();
  await page.keyboard.type('Neumann');
  await page.locator('.q-menu .q-item', { hasText: 'Neumann' }).first().click();
  await expect
    .poll(async () =>
      ((await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json()) as any[])[0]
        ?.channels[0],
    )
    .toMatchObject({ device: 'Neumann' });

  // stand: no local devices, so a typed name becomes the stand type
  await stand.click();
  await page.keyboard.type('K&M 210');
  await page.locator('.q-menu .q-item', { hasText: 'K&M 210' }).first().click();
  await expect
    .poll(async () =>
      ((await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json()) as any[])[0]
        ?.channels[0],
    )
    .toMatchObject({ stand_type: 'K&M 210' });
});

test('a stagebox can be cascaded into another stagebox over dSnake (expansion port)', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId } = await seed(request, headers);
  // A console with a dSnake input so the quick-connect card's default target exists. Devices must be
  // created through the graph endpoint (not the legacy audio endpoint) so `kind` is honoured — the
  // legacy route drops `kind` and the console card's `isStagebox` check then never matches.
  await call(request, headers, 'post', `/jobs/${jobId}/graph/devices`, {
    name: 'GLD-80',
    domain: 'audio',
    kind: 'mixer',
    ports: [{ id: 'dsnake-in', direction: 'in', signal: 'data', connector: 'dsnake' }],
  });
  // AR2412: a stagebox with a dSnake output AND a dSnake expansion input (the cascade target).
  const ar2412 = await call(request, headers, 'post', `/jobs/${jobId}/graph/devices`, {
    name: 'AR2412',
    domain: 'audio',
    kind: 'digital_stagebox',
    ports: [
      { id: 'dsnake-out', direction: 'out', signal: 'data', connector: 'dsnake' },
      { id: 'dsnake-exp-in', direction: 'in', signal: 'data', connector: 'dsnake', label: 'dSnake Expander' },
    ],
  });
  // AR84: a stagebox with only a dSnake output — the one we cascade into the AR2412.
  const ar84 = await call(request, headers, 'post', `/jobs/${jobId}/graph/devices`, {
    name: 'AR84',
    domain: 'audio',
    kind: 'digital_stagebox',
    ports: [{ id: 'dsnake-out', direction: 'out', signal: 'data', connector: 'dsnake' }],
  });

  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  const panel = page.getByTestId('console-panel');
  await expect(panel).toBeVisible();
  // The stagebox quick-connect card lives on the "patch" tab; make sure it is the active panel.
  await page.getByTestId('console-tab-patch').click();

  // Both stageboxes are listed as unconnected; scope to the AR84 row.
  const rows = panel.getByTestId('console-unconnected-stageboxes');
  const ar84Row = rows.locator('div.row').filter({ hasText: 'AR84' });
  await expect(ar84Row).toBeVisible();

  // Pick the cascade target (another stagebox) instead of the console.
  await ar84Row.getByTestId('console-stagebox-target').click();
  await page.getByRole('option', { name: 'AR2412' }).click();
  // The destination port is now the AR2412's expansion input; it is auto-selected on target change.
  await expect(ar84Row.getByTestId('console-stagebox-dst-port')).toHaveValue(
    new RegExp('Expander', 'i'),
  );

  // Wait for the connect call itself: reading the graph straight after the click races the save.
  const connectResponse = page.waitForResponse(
    (r) => r.url().includes('/connect-stagebox') && r.request().method() === 'POST',
  );
  await ar84Row.getByTestId('console-connect-stagebox').click();
  const connected = await connectResponse;
  expect(connected.status(), await connected.text()).toBeLessThan(300);

  // The link is a data edge AR84 -> AR2412, not through the console.
  type Edge = { signal: string; src_device_id: string; dst_device_id: string };
  const edges = (await (
    await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })
  ).json()) as { edges: Edge[] };
  const link = edges.edges.find((e) => e.src_device_id === ar84.id && e.dst_device_id === ar2412.id);
  expect(link, 'expected an AR84 -> AR2412 data edge').toBeDefined();
  expect(link!.signal).toBe('data');

  // The AR84 card flips to the linked state.
  await expect(rows.locator('div.row').filter({ hasText: 'AR84' }).getByTestId('console-stagebox-linked')).toBeVisible();
});
