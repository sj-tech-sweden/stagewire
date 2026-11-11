import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

async function post(
  request: APIRequestContext,
  headers: Record<string, string>,
  path: string,
  data: object,
) {
  const res = await request.post(`${API_BASE}/api/v1${path}`, { headers, data });
  expect(res.status(), `${path}: ${await res.text()}`).toBeLessThan(300);
  return res.json();
}

test('a crew member opens the read-only mobile view with a share token and no login', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share E2E ${Date.now()}` })).id;
  await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Stagebox A',
    kind: 'stagebox',
    attributes: { network_ip: '192.168.1.10', network_vlan: 120 },
  });

  // A logged-in user mints the share token; it is the only credential the crew view needs.
  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  expect(share.status()).toBe(200);
  const { token } = await share.json();
  expect(token).toBeTruthy();

  // The crew member lands straight on the view — no session, no login redirect.
  await page.goto(`/jobs/${jobId}/view?token=${token}`);
  const list = page.getByTestId('share-device-list');
  await expect(list).toBeVisible();
  await expect(page.getByText('Stagebox A')).toBeVisible();
  // Network metadata is surfaced read-only inside the expanded device detail.
  await page.locator('.q-expansion-item', { hasText: 'Stagebox A' }).click();
  await expect(page.getByText('192.168.1.10')).toBeVisible();

  // No editing affordances leak into the read-only view.
  await expect(page.getByTestId('inspector-name')).toHaveCount(0);
});

test('the mobile view rejects a missing or forged token', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share E2E ${Date.now()}` })).id;

  // No token at all.
  await page.goto(`/jobs/${jobId}/view`);
  await expect(page.getByTestId('share-error')).toBeVisible();

  // A tampered token.
  await page.goto(`/jobs/${jobId}/view?token=not-a-real-token`);
  await expect(page.getByTestId('share-error')).toBeVisible();
});

test('the workspace can generate a shareable QR + link for the crew view', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share E2E ${Date.now()}` })).id;

  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('open-share').click();
  await expect(page.getByTestId('share-qr')).toBeVisible();
  const link = await page.getByTestId('share-link').inputValue();
  expect(link).toContain(`/jobs/${jobId}/view?token=`);

  // Following the generated link opens the read-only view.
  await page.goto(link);
  await expect(page.getByTestId('share-device-list')).toBeVisible();
});

test('a keyboard-wedge scan in the crew view looks up the matched device', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share E2E ${Date.now()}` })).id;
  await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Stagebox A',
    kind: 'stagebox',
    attributes: { stockwire_asset_id: 'ASSET-123' },
  });

  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  const { token } = await share.json();
  await page.goto(`/jobs/${jobId}/view?token=${token}`);
  await expect(page.getByTestId('share-device-list')).toBeVisible();

  // Switch to the scan tab and feed a code through the keyboard-wedge input.
  await page.getByTestId('share-tab-scan').click();
  await expect(page.getByTestId('share-scan')).toBeVisible();
  await page.getByTestId('scan-keyboard-input').fill('ASSET-123');
  await page.getByTestId('scan-keyboard-input').press('Enter');

  const result = page.getByTestId('share-scan-result');
  await expect(result).toBeVisible();
  await expect(result).toContainText('ASSET-123');
  await expect(result).toContainText('Stagebox A');
});

test('a workspace user can bind a Stockwire asset to a device and see it read-only', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Bind E2E ${Date.now()}` })).id;
  await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Stagebox A',
    kind: 'stagebox',
  });

  await page.goto(`/jobs/${jobId}/workspace`);

  // Open the device in the inspector from the workspace table (a lone device has no patch edges).
  // The table rows are keyed by kind (e.g. "stagebox"), not the device name.
  await page.getByTestId('mode-toggle').getByText(/all gear|all utrustning/i).click();
  const row = page
    .getByTestId('workspace-table')
    .locator('tbody tr')
    .filter({ hasText: 'stagebox' })
    .first();
  await row.locator('td').nth(1).click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Stagebox A');
  await expect(page.getByTestId('stockwire-asset-panel')).toBeVisible();

  // Bind a Stockwire asset (the integration is off in e2e, so the code is stored locally).
  await page.getByTestId('bind-open').click();
  await expect(page.getByTestId('bind-code')).toBeVisible();
  await page.getByTestId('bind-code').fill('ASSET-XYZ');
  await page.getByTestId('bind-confirm').click();
  await expect(page.getByTestId('bind-result')).toBeVisible();

  // Close the dialog; the inspector now shows the bound asset and an unbind action.
  await page.getByTestId('bind-dismiss').click();
  await expect(page.getByTestId('stockwire-asset-panel')).toContainText('ASSET-XYZ');
  await expect(page.getByTestId('bind-unbind')).toBeVisible();

  // The crew view reflects the binding read-only.
  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  const { token } = await share.json();
  await page.goto(`/jobs/${jobId}/view?token=${token}`);
  await expect(page.getByTestId('share-device-list')).toBeVisible();
  // The bound asset code is surfaced inside the expanded device detail in the crew view.
  await page.locator('.q-expansion-item', { hasText: 'Stagebox A' }).click();
  await expect(page.getByText('ASSET-XYZ')).toBeVisible();

  // Scanning the bound code on the crew view locates the device (the High fix: lookup by the
  // scanned code, not the resolved Stockwire id).
  await page.getByTestId('share-tab-scan').click();
  await expect(page.getByTestId('share-scan')).toBeVisible();
  await page.getByTestId('scan-keyboard-input').fill('ASSET-XYZ');
  await page.getByTestId('scan-keyboard-input').press('Enter');
  const result = page.getByTestId('share-scan-result');
  await expect(result).toBeVisible();
  await expect(result).toContainText('Stagebox A');
});

test('the crew view receives new gear live over the websocket, without a reload', async ({ page, request, context }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share live ${Date.now()}` })).id as string;
  // Seed a device so the crew view has content, then mint a read-only share token.
  await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Stagebox A', device_type: 'stagebox' });
  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  const { token } = await share.json();
  expect(token).toBeTruthy();

  // Crew member opens the read-only view with only the share token (no session).
  const crew = await context.newPage();
  await crew.goto(`/jobs/${jobId}/view?token=${token}`);
  await expect(crew.getByTestId('share-device-list')).toBeVisible();
  await expect(crew.getByText('Stagebox A')).toBeVisible();
  // Wait until the crew socket is actually connected, so the next event is delivered live (the
  // websocket only broadcasts to currently-connected clients, so a post before connect would be missed).
  await expect(crew.locator('[data-socket]').first()).toHaveAttribute('data-socket', 'open');

  // The editor adds another device; the crew view should surface it live, not after a manual refresh.
  await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Monitor Wedge', device_type: 'other' });
  await expect(crew.getByText('Monitor Wedge')).toBeVisible({ timeout: 20000 });
});

test('the crew list shows only real gear, not channels, buses or channel lists', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share filter ${Date.now()}` })).id;
  // A channel list (and its channels) are structural, not gear — they must not appear in the crew list.
  const list = await post(request, headers, `/jobs/${jobId}/graph/lists`, { name: 'FOH' });
  await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'FOH List',
    kind: 'channel_list',
    attributes: { channel_list_id: list.id },
  });
  await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Ch 1',
    kind: 'channel',
    attributes: { list_id: list.id, channel_number: 1 },
  });
  // A real, placed piece of gear is what the crew should see.
  await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Lead Mic',
    kind: 'mic',
    canvas_x_cm: 200,
    canvas_y_cm: 200,
  });

  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  const { token } = await share.json();
  await page.goto(`/jobs/${jobId}/view?token=${token}`);
  const listPanel = page.getByTestId('share-device-list');
  await expect(listPanel).toBeVisible();
  await expect(listPanel.getByText('Lead Mic')).toBeVisible();
  // Structural nodes are filtered out of the crew gear list.
  await expect(listPanel.getByText('FOH List')).toHaveCount(0);
  await expect(listPanel.getByText('Ch 1')).toHaveCount(0);
});

test('the crew map reuses the workspace canvas and opens a read-only inspector on tap', async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share map ${Date.now()}` })).id;
  // Place a single piece of gear at the centre of the (default) 1000x600 stage.
  await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Stage Mic',
    kind: 'mic',
    canvas_x_cm: 500,
    canvas_y_cm: 300,
  });

  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  const { token } = await share.json();
  await page.goto(`/jobs/${jobId}/view?token=${token}`);
  await page.getByTestId('share-tab-map').click();

  // The map is the same Konva canvas the editor uses, with gear drawn on it.
  const canvas = page.getByTestId('workspace-canvas');
  await expect(canvas).toBeVisible();
  await expect(canvas).toHaveAttribute('data-canvas-devices', '1');

  // Tap the device to open its read-only inspector. Click by a position relative to the canvas
  // surface (the standalone page can overflow horizontally, so viewport maths would miss).
  const zoom = Number(await canvas.getAttribute('data-zoom'));
  const [panX, panY] = (await canvas.getAttribute('data-pan'))!.split(',').map(Number);
  const rx = panX + 500 * zoom + 30 * zoom;
  const ry = panY + 300 * zoom + 15 * zoom;
  await canvas.click({ position: { x: rx, y: ry } });

  const detail = page.getByTestId('share-map-detail');
  await expect(detail).toBeVisible();
  await expect(detail.getByTestId('inspector-name')).toHaveValue('Stage Mic');
  // Read-only: the edit-details affordance is not offered.
  await expect(detail.getByTestId('inspector-edit-details')).toHaveCount(0);
});

test('the crew device list opens the full read-only inspector', async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share list-inspect ${Date.now()}` })).id;
  const gear = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Stagebox A',
    kind: 'stagebox',
  });

  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  const { token } = await share.json();
  await page.goto(`/jobs/${jobId}/view?token=${token}`);

  // The list tab is the default; each row has an "open" action that opens the full inspector.
  const listPanel = page.getByTestId('share-device-list');
  await expect(listPanel.getByText('Stagebox A')).toBeVisible();
  await listPanel.getByTestId(`share-device-inspect-${gear.id}`).click();

  // The dialog shows the same read-only inspector the map/patch tabs use (name editable=false).
  const dialog = page.getByTestId('inspector-name');
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveValue('Stagebox A');
});

test('the crew patch tab shows the full patch list, read-only', async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share patch ${Date.now()}` })).id;

  // Two real pieces of gear, patched together with an audio cable.
  const mic = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Lead Mic',
    kind: 'mic',
  });
  const wedge = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Monitor Wedge',
    kind: 'speaker',
  });
  await post(
    request,
    headers,
    `/jobs/${jobId}/graph/edges?force=true`,
    {
      signal: 'audio',
      src_device_id: mic.id,
      src_port: 'out',
      dst_device_id: wedge.id,
      dst_port: 'in',
      channels: 1,
    },
  );

  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  const { token } = await share.json();
  await page.goto(`/jobs/${jobId}/view?token=${token}`);

  // The patch tab renders the full multi-domain patch table, read-only.
  await page.getByTestId('share-tab-patch').click();
  const table = page.getByTestId('patch-table');
  await expect(table).toBeVisible();
  // The connection is listed (from the mic, to the wedge).
  await expect(table.getByText('Lead Mic')).toBeVisible();
  await expect(table.getByText('Monitor Wedge')).toBeVisible();
  // Read-only: no per-row delete action is offered.
  await expect(table.getByRole('button', { name: /remove/i })).toHaveCount(0);

  // Tapping a device link selects it and opens its read-only inspector.
  await table.getByRole('button', { name: 'Lead Mic' }).click();
  const detail = page.getByTestId('share-patch-detail');
  await expect(detail).toBeVisible();
  await expect(detail.getByTestId('inspector-name')).toHaveValue('Lead Mic');
  // Read-only: the edit-details affordance is not offered.
  await expect(detail.getByTestId('inspector-edit-details')).toHaveCount(0);
});

test('a channel in the crew patch tab opens as its own device, not a mixer port', async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share channel ${Date.now()}` })).id;

  // A channel list, its channel node (not gear), and the real mic it feeds.
  const list = await post(request, headers, `/jobs/${jobId}/graph/lists`, { name: 'FOH' });
  const channel = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Ch 1',
    kind: 'channel',
    attributes: { list_id: list.id, channel_number: 1 },
  });
  const mic = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Lead Mic',
    kind: 'mic',
  });
  await post(
    request,
    headers,
    `/jobs/${jobId}/graph/edges?force=true`,
    {
      signal: 'audio',
      src_device_id: channel.id,
      src_port: 'out',
      dst_device_id: mic.id,
      dst_port: 'in',
      channels: 1,
    },
  );

  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  const { token } = await share.json();
  await page.goto(`/jobs/${jobId}/view?token=${token}`);

  // The channel is filtered out of the gear list (it is not gear)...
  await expect(page.getByTestId('share-device-list').getByText('Ch 1')).toHaveCount(0);
  // ...but is a first-class row in the patch tab, so a crew member can trace it.
  await page.getByTestId('share-tab-patch').click();
  const table = page.getByTestId('patch-table');
  await expect(table).toBeVisible();
  await expect(table.getByText('Ch 1')).toBeVisible();

  // Tapping the channel opens its own device inspector (read-only), proving channels
  // behave as devices here rather than as ports nested under a mixer.
  await table.getByRole('button', { name: 'Ch 1' }).click();
  const detail = page.getByTestId('share-patch-detail');
  await expect(detail).toBeVisible();
  await expect(detail.getByTestId('inspector-name')).toHaveValue('Ch 1');
  await expect(detail.getByTestId('inspector-edit-details')).toHaveCount(0);
});

test('a crew share link carries its creator locale and renders the UI in that language', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share locale ${Date.now()}` })).id;

  // Mint the share link with the creator's locale embedded in the token.
  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, {
    headers,
    params: { locale: 'sv' },
  });
  const { token } = await share.json();
  await page.goto(`/jobs/${jobId}/view?token=${token}`);

  // The view applies the link's locale before it renders: the document language flips to Swedish.
  await expect
    .poll(async () => page.evaluate(() => document.documentElement.lang))
    .toBe('sv');
  // And a localised string is actually shown (not just the lang attribute).
  await expect(page.getByText('Skrivskyddad')).toBeVisible();
});
