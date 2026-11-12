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

test('a keyboard-wedge scan opens the matched inspector and signal-flow diagram', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  await page.setViewportSize({ width: 390, height: 844 });
  const jobId = (await post(request, headers, '/jobs', { title: `Share E2E ${Date.now()}` })).id;
  const mic = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Lead Mic',
    kind: 'mic',
    ports: [{ id: 'out', direction: 'out', label: 'Mic out', connector: 'XLR3' }],
  });
  const stagebox = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Stagebox A',
    kind: 'stagebox',
    ports: [
      { id: 'in', direction: 'in', label: 'Box in', connector: 'XLR3' },
      { id: 'out', direction: 'out', label: 'Box out', connector: 'XLR3' },
    ],
    attributes: {
      stockwire_asset_code: 'ASSET-123',
      stockwire_asset_tag: 'TAG-123',
      stockwire_asset_serial: 'SN-123',
      stockwire_asset_barcode: 'BAR-123',
      stockwire_asset_qr_code: 'QR-123',
      stockwire_asset_rfid: 'RFID-123',
    },
    stockwire_device_id: 'SW-DEV-456',
  });
  const wedge = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Monitor Wedge',
    kind: 'speaker',
    ports: [{ id: 'in', direction: 'in', label: 'Wedge in', connector: 'XLR3' }],
  });
  const list = await post(request, headers, `/jobs/${jobId}/graph/lists`, { name: 'FOH' });
  const channel = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Ch 1',
    kind: 'channel',
    attributes: { list_id: list.id, channel_number: 1, source_device_id: mic.id },
  });
  await post(request, headers, `/jobs/${jobId}/graph/edges?force=true`, {
    signal: 'audio',
    src_device_id: mic.id,
    src_port: 'out',
    dst_device_id: stagebox.id,
    dst_port: 'in',
    channels: 1,
  });
  await post(request, headers, `/jobs/${jobId}/graph/edges?force=true`, {
    signal: 'audio',
    src_device_id: stagebox.id,
    src_port: 'out',
    dst_device_id: channel.id,
    dst_port: 'in',
    channels: 1,
    attributes: {
      chain: channel.id,
      position: 0,
      patch_label: 'Vocal feed',
      connector: 'XLR3',
    },
  });
  await post(request, headers, `/jobs/${jobId}/graph/edges?force=true`, {
    signal: 'audio',
    src_device_id: channel.id,
    src_port: 'out',
    dst_device_id: wedge.id,
    dst_port: 'in',
    channels: 1,
    attributes: { patch_label: 'Monitor send', connector: 'XLR3' },
  });

  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  const { token } = await share.json();
  await page.goto(`/jobs/${jobId}/view?token=${token}`);
  await expect(page.getByTestId('share-device-list')).toBeVisible();

  // Switch to the scan tab and feed a code through the keyboard-wedge input.
  await page.getByTestId('share-tab-scan').click();
  await expect(page.getByTestId('share-scan')).toBeVisible();
  const result = page.getByTestId('share-scan-result');
  const inspectorName = page.getByTestId('inspector-name');
  const scanCodes = ['ASSET-123', 'SW-DEV-456', 'TAG-123', 'SN-123', 'BAR-123', 'QR-123', 'RFID-123'];
  for (const [index, code] of scanCodes.entries()) {
    if (index > 0) {
      await page.keyboard.press('Escape');
      await expect(inspectorName).toBeHidden();
    }
    await page.getByTestId('scan-keyboard-input').fill(code);
    await page.getByTestId('scan-keyboard-input').press('Enter');
    await expect(result).toBeVisible();
    await expect(result).toContainText(code);
    await expect(result).toContainText('Stagebox A');
    await expect(inspectorName).toHaveValue('Stagebox A');

    if (index === 0) {
      const flow = page.getByTestId('signal-flow-diagram');
      await expect(flow).toBeVisible();
      await expect(flow).toContainText('Lead Mic');
      await expect(flow).toContainText('Monitor Wedge');
      await expect(flow).toContainText('Vocal feed');
      await expect(flow).toContainText('Monitor send');
      await expect(flow).toContainText('XLR3');
      const dimensions = await flow.evaluate((element) => {
        const scrollable = element.querySelector('.dmx-flow-scroll');
        return {
          clientWidth: scrollable.clientWidth,
          scrollWidth: scrollable.scrollWidth,
          documentWidth: document.documentElement.scrollWidth,
          viewportWidth: document.documentElement.clientWidth,
        };
      });
      expect(dimensions.scrollWidth).toBeGreaterThan(dimensions.clientWidth);
      expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
    }
  }
});

test('a product ID scan lets crew choose between matching devices', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share scan choice ${Date.now()}` })).id;
  const first = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Stagebox A',
    kind: 'stagebox',
    stockwire_product_id: 'PRODUCT-77',
    stockwire_product_name: 'Stagebox',
  });
  const second = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Stagebox B',
    kind: 'stagebox',
    stockwire_product_id: 'PRODUCT-77',
    stockwire_product_name: 'Stagebox',
  });
  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  const { token } = await share.json();
  await page.goto(`/jobs/${jobId}/view?token=${token}`);
  await page.getByTestId('share-tab-scan').click();
  await page.getByTestId('scan-keyboard-input').fill('PRODUCT-77');
  await page.getByTestId('scan-keyboard-input').press('Enter');

  const candidates = page.getByTestId('share-scan-candidates');
  await expect(candidates).toBeVisible();
  await expect(candidates.getByTestId(`scan-match-${first.id}`)).toBeVisible();
  await expect(candidates.getByTestId(`scan-match-${second.id}`)).toBeVisible();
  await expect(page.getByTestId('inspector-name')).toHaveCount(0);

  await candidates.getByTestId(`scan-match-${second.id}`).click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Stagebox B');
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

test('workspace unbinding clears all Stockwire scan identifiers', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Unbind E2E ${Date.now()}` })).id;
  const device = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Bound Stagebox',
    kind: 'stagebox',
    stockwire_device_id: 'OLD-DEVICE-ID',
    attributes: {
      stockwire_asset_id: 'OLD-ASSET-ID',
      stockwire_asset_code: 'OLD-CODE',
      stockwire_asset_tag: 'OLD-TAG',
      stockwire_asset_serial: 'OLD-SERIAL',
      stockwire_asset_barcode: 'OLD-BARCODE',
      stockwire_asset_qr_code: 'OLD-QR',
      stockwire_asset_rfid: 'OLD-RFID',
      stockwire_asset_description: 'Old asset',
    },
  });

  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/all gear|all utrustning/i).click();
  const row = page
    .getByTestId('workspace-table')
    .locator('tbody tr')
    .filter({ hasText: 'stagebox' })
    .first();
  await row.locator('td').nth(1).click();
  const assetPanel = page.getByTestId('stockwire-asset-panel');
  await expect(assetPanel).toContainText('OLD-RFID');

  await page.getByTestId('bind-unbind').click();
  await expect(page.getByTestId('bind-unbind')).toHaveCount(0);
  for (const code of ['OLD-CODE', 'OLD-TAG', 'OLD-SERIAL', 'OLD-BARCODE', 'OLD-QR', 'OLD-RFID']) {
    await expect(assetPanel).not.toContainText(code);
  }

  const response = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers });
  expect(response.status()).toBe(200);
  const updated = (await response.json()).devices.find((item) => item.id === device.id);
  expect(updated.stockwire_device_id).toBeNull();
  for (const key of [
    'stockwire_asset_id',
    'stockwire_asset_code',
    'stockwire_asset_tag',
    'stockwire_asset_serial',
    'stockwire_asset_barcode',
    'stockwire_asset_qr_code',
    'stockwire_asset_rfid',
    'stockwire_asset_description',
  ]) {
    expect(updated.attributes[key]).toBeNull();
  }
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
    attributes: {
      stockwire_asset_code: 'ASSET-INSPECTOR',
      stockwire_asset_tag: 'TAG-INSPECTOR',
    },
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
  await expect(page.getByTestId('stockwire-asset-panel')).toBeVisible();
  await expect(page.getByTestId('stockwire-asset-panel')).toContainText('ASSET-INSPECTOR');
  await expect(page.getByTestId('stockwire-asset-panel')).toContainText('TAG-INSPECTOR');
  await expect(page.getByTestId('bind-open')).toHaveCount(0);
});

test('a crew share link can bind and unbind an asset only when the creator allows it', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Crew asset bind ${Date.now()}` })).id;
  const device = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Stagebox A',
    kind: 'stagebox',
  });

  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('open-share').click();
  await expect(page.getByTestId('share-qr')).toBeVisible();
  const readOnlyLink = await page.getByTestId('share-link').inputValue();
  const readOnlyToken = new URL(readOnlyLink).searchParams.get('token');
  const readOnlyView = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/mobile-view`, {
    params: { token: readOnlyToken },
  });
  expect((await readOnlyView.json()).can_bind_assets).toBe(false);

  const generatedLinkCanBind = async () => {
    const currentLink = await page.getByTestId('share-link').inputValue();
    if (!currentLink) return false;
    const token = new URL(currentLink).searchParams.get('token');
    if (!token) return false;
    const response = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/mobile-view`, {
      params: { token },
    });
    return response.ok() && (await response.json()).can_bind_assets === true;
  };

  await page.getByTestId('share-allow-asset-binding').click();
  await expect.poll(generatedLinkCanBind).toBe(true);
  let link = await page.getByTestId('share-link').inputValue();
  expect(link).not.toBe(readOnlyLink);
  let token = new URL(link).searchParams.get('token');
  let view = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/mobile-view`, {
    params: { token },
  });
  expect((await view.json()).can_bind_assets).toBe(true);

  // The dialog remembers the per-job choice and mints a link with the same capability again.
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('share-qr')).toHaveCount(0);
  await page.getByTestId('open-share').click();
  await expect.poll(generatedLinkCanBind).toBe(true);
  link = await page.getByTestId('share-link').inputValue();
  token = new URL(link).searchParams.get('token');
  view = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/mobile-view`, {
    params: { token },
  });
  expect((await view.json()).can_bind_assets).toBe(true);

  await page.goto(link);
  await expect(page.getByTestId('share-device-list')).toBeVisible();
  await page.getByTestId(`share-device-inspect-${device.id}`).click();
  const assetPanel = page.getByTestId('stockwire-asset-panel');
  const bindButton = assetPanel.getByTestId('bind-open');
  await expect(assetPanel).toBeVisible();
  await expect(bindButton).toBeVisible();
  await bindButton.click();
  await page.getByTestId('bind-code').fill('CREW-ASSET-1');
  await page.getByTestId('bind-confirm').click();
  await expect(page.getByTestId('bind-result')).toBeVisible();
  await page.getByTestId('bind-dismiss').click();
  await expect(page.getByTestId('stockwire-asset-panel')).toContainText('CREW-ASSET-1');

  await page.getByTestId('bind-unbind').click();
  await expect(page.getByTestId('bind-open')).toBeVisible();
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
    stockwire_product_id: '77',
    ports: [{ id: 'out', direction: 'out', signal: 'audio', connector: 'XLR3' }],
  });
  const wedge = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Monitor Wedge',
    kind: 'speaker',
    stockwire_product_id: '88',
    ports: [{ id: 'in', direction: 'in', signal: 'audio', connector: 'XLR3' }],
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
      attributes: { patch_label: 'Stage Left', connector: 'XLR3' },
    },
  );

  await page.route('**/stockwire-assets**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.includes(mic.id)) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [{
            id: 'asset-77',
            product_id: '77',
            asset_tag: 'TAG-77',
            barcode: 'BAR-77',
            qr_code: 'QR-77',
            rfid: 'RFID-77',
          }],
        }),
      });
    } else {
      await route.fulfill({ status: 502, contentType: 'application/json', body: '{}' });
    }
  });

  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, {
    headers,
    params: { allow_asset_binding: true },
  });
  const { token } = await share.json();
  await page.goto(`/jobs/${jobId}/view?token=${token}`);

  // The list detail and its inspector share the same graph snapshot as the patch tab.
  const micRow = page.getByTestId(`share-device-${mic.id}`);
  await micRow.click();
  await expect(micRow.getByTestId('share-patch-points')).toContainText('Stage Left');
  await micRow.getByTestId('share-detail-inspect').click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Lead Mic');
  await expect(page.getByTestId('inspector-connections')).toContainText('Stage Left');
  await page.keyboard.press('Escape');

  // The patch tab renders the full multi-domain patch table, read-only.
  await page.getByTestId('share-tab-patch').click();
  const table = page.getByTestId('patch-table');
  await expect(table).toBeVisible();
  // The connection is listed (from the mic, to the wedge).
  await expect(table.getByText('Lead Mic')).toBeVisible();
  await expect(table.getByText('Monitor Wedge')).toBeVisible();
  await expect(table.getByText('Stage Left')).toBeVisible();
  // Read-only: no per-row delete action is offered.
  await expect(table.getByRole('button', { name: /remove/i })).toHaveCount(0);

  // Tapping a device link selects it and opens its read-only inspector.
  await table.getByRole('button', { name: 'Lead Mic' }).click();
  const detail = page.getByTestId('share-patch-detail');
  await expect(detail).toBeVisible();
  await expect(detail.getByTestId('inspector-name')).toHaveValue('Lead Mic');
  // Read-only: the edit-details affordance is not offered.
  await expect(detail.getByTestId('inspector-edit-details')).toHaveCount(0);

  await detail.getByTestId('bind-open').click();
  await expect(page.getByTestId('bind-product-device')).toBeEnabled();
  await page.getByTestId('bind-product-device').click();
  const assetOption = page.getByRole('option').filter({ hasText: 'TAG-77' });
  await expect(assetOption).toContainText('BAR-77');
  await expect(assetOption).toContainText('QR-77');
  await expect(assetOption).toContainText('RFID-77');
  await assetOption.click();
  await page.getByTestId('bind-confirm').click();
  await expect(page.getByTestId('bind-result')).toContainText('BAR-77');
  await page.getByTestId('bind-dismiss').click();
  await expect(detail.getByTestId('stockwire-asset-panel')).toContainText('RFID-77');

  await table.getByRole('button', { name: 'Monitor Wedge' }).click();
  await expect(detail.getByTestId('inspector-name')).toHaveValue('Monitor Wedge');
  await detail.getByTestId('bind-open').click();
  await expect(page.locator('.q-banner.bg-negative')).toBeVisible();
  await page.getByTestId('bind-product-device').click();
  await expect(
    page.getByText(/No Stockwire assets found for this product|Inga Stockwire-enheter hittades för denna produkt/),
  ).toBeVisible();
  await expect(page.getByRole('option').filter({ hasText: 'TAG-77' })).toHaveCount(0);
});

test('a channel in the crew patch tab opens as its own device, not a mixer port', async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share channel ${Date.now()}` })).id;

  // A native channel node (not gear) and the mic feeding it.
  const list = await post(request, headers, `/jobs/${jobId}/graph/lists`, { name: 'FOH' });
  const channel = await post(request, headers, `/jobs/${jobId}/graph/lists/${list.id}/channels`, {
    source_label: 'Ch 1',
  });
  const mic = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Lead Mic',
    kind: 'mic',
    ports: [{ id: 'out', direction: 'out', signal: 'audio', connector: 'XLR3' }],
  });
  await post(
    request,
    headers,
    `/jobs/${jobId}/graph/edges?force=true`,
    {
      signal: 'audio',
      src_device_id: mic.id,
      src_port: 'out',
      dst_device_id: channel.id,
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
