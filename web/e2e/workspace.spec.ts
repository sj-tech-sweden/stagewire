import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, enableStockwire, setStockwireEnabled, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

async function post(request: APIRequestContext, headers: Record<string, string>, path: string, data: object) {
  const res = await request.post(`${API_BASE}/api/v1${path}`, { headers, data });
  expect(res.status(), `${path}: ${await res.text()}`).toBeLessThan(300);
  return res.json();
}

const dataRows = (page: Page) =>
  page.getByTestId('workspace-table').locator('tbody tr').filter({ has: page.locator('input') });

// Fit the plot and read the zoom it settled on, so pixel positions can be derived from cm.
async function fittedZoom(page: Page) {
  await page.getByTestId('canvas-fit').click();
  return Number(await page.getByTestId('workspace-canvas').getAttribute('data-zoom'));
}

async function seedGraph(page: Page, request: APIRequestContext) {
  // CI seeds the stockwire integration disabled; enable it so the stockwire-dependent UI under test is present.
  await enableStockwire(request);
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Workspace ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const mic = await post(request, headers, `${g}/devices`, {
    domain: 'audio',
    name: 'Lead mic',
    ports: [{ id: 'out', direction: 'out', signal: 'audio', connector: 'xlr3' }],
    stockwire_product_id: '4242',
    stockwire_product_name: 'SM58',
    stockwire_booked: false,
  });
  const box = await post(request, headers, `${g}/devices`, {
    domain: 'audio',
    name: 'Stagebox',
    ports: [{ id: 'in', direction: 'in', signal: 'audio', connector: 'xlr3', channels: 32 }],
  });
  await post(request, headers, `${g}/edges`, {
    signal: 'audio',
    src_device_id: mic.id,
    src_port: 'out',
    dst_device_id: box.id,
    dst_port: 'in',
  });
  return { jobId, headers, mic, box };
}

test('the workspace opens as a canvas with the stage and venue; only placed gear is on the plot', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  const { jobId, headers, mic } = await seedGraph(page, request);
  const frameLoaded = page.waitForResponse((res) => res.url().endsWith(`/jobs/${jobId}/power-outlets`));
  await page.goto(`/jobs/${jobId}/workspace`);
  await frameLoaded;

  await expect(page.getByTestId('workspace-canvas')).toBeVisible();
  const graphOf = async () => (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })).json();
  await expect(page.getByTestId('place-gear')).toHaveCount(2);
  expect((await graphOf()).devices.every((d: { canvas_x_cm: number | null }) => d.canvas_x_cm === null)).toBe(true);

  await page.getByTestId('place-gear').filter({ hasText: 'Lead mic' }).click();
  await expect(page.getByTestId('place-gear')).toHaveCount(1);
  await expect
    .poll(async () => (await graphOf()).devices.find((d: { id: string }) => d.id === mic.id).canvas_x_cm)
    .not.toBeNull();

  await page.getByTestId('layer-coverage').click();
  await page.getByTestId('layer-outlets').click();
  await page.getByTestId('canvas-fit').click();

  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();
  await expect(page.getByTestId('workspace-table')).toBeVisible();
  await expect(dataRows(page)).toHaveCount(2);
  await expect(page.getByRole('button', { name: /request to add to stockwire job booking/i })).toBeVisible();

  const kept = (await graphOf()).devices.find((d: { id: string }) => d.id === mic.id);
  expect(kept.stockwire_product_id).toBe('4242');
});

test('the patch drawer lists connections per domain and the inspector shows the trace', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  const { jobId } = await seedGraph(page, request);
  await page.goto(`/jobs/${jobId}/workspace`);

  const table = page.getByTestId('patch-table');
  await expect(table.getByText('Lead mic')).toBeVisible();
  await expect(table.getByText('Stagebox')).toBeVisible();

  // a device in the drawer is edited from there: its name opens the inspector
  await page.getByTestId('patch-edit-from').first().click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Lead mic');
  await page.getByTestId('patch-tab-power').click();
  await expect(page.getByText(/no connections in this domain yet|inga kopplingar/i)).toBeVisible();

  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();
  await dataRows(page).first().locator('td').nth(1).click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Lead mic');
});

test('the inspector shows a Network & Control panel for AVL devices and hides it for power', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  const { jobId, headers, mic } = await seedGraph(page, request);
  // a power device has no networked control panel
  const power = await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'power',
    name: 'Distro',
    kind: 'distro',
  });
  await page.goto(`/jobs/${jobId}/workspace`);

  // Open the audio device (AVL domain) in the inspector.
  await page.getByTestId('patch-edit-from').first().click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Lead mic');
  await expect(page.getByTestId('network-panel')).toBeVisible();

  // Set the network fields.
  await page.getByTestId('network-panel').click();
  const ip = page.getByTestId('network-ip');
  await ip.fill('192.168.1.50');
  await ip.press('Enter');
  await page.getByTestId('network-subnet').fill('255.255.255.0');
  await page.getByTestId('network-subnet').press('Enter');
  await page.getByTestId('network-vlan').fill('120');
  await page.getByTestId('network-vlan').press('Enter');

  // The quick-launch link points at the device's management page.
  const launch = page.getByTestId('network-open-webui');
  await expect(launch).toBeVisible();
  await expect(launch).toHaveAttribute('href', 'http://192.168.1.50');

  // Protocols are a multiselect; picking Dante persists the whole list.
  await page.getByTestId('network-protocols').click();
  await page.locator('.q-menu .q-item', { hasText: 'Dante' }).click();
  // close the select popup
  await page.keyboard.press('Escape');

  // Backend holds the AVL network metadata on the device attributes.
  const graph = (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })).json();
  await expect
    .poll(async () => (await graph).devices.find((d: { id: string }) => d.id === mic.id).attributes)
    .toMatchObject({ network_ip: '192.168.1.50', network_subnet: '255.255.255.0', network_vlan: 120, network_protocols: ['dante'] });

  // Switching to the power device hides the panel entirely.
  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();
  await dataRows(page).filter({ hasText: 'Distro' }).locator('td').nth(1).click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Distro');
  await expect(page.getByTestId('network-panel')).toHaveCount(0);
});


test('layer toggles and the catalog drawer open', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  const { jobId } = await seedGraph(page, request);
  await page.goto(`/jobs/${jobId}/workspace`);

  await page.getByTestId('layer-audio').click();
  await page.getByTestId('layer-audio').click();
  await expect(page.getByTestId('phase-L1')).toBeVisible();

  await page.getByTestId('open-catalog').click();
  await expect(page.getByTestId('catalog-search')).toBeVisible();
  // The drawer's availability controls render once the catalog loads (date-range support is
  // reported by Stockwire, so the legacy "not available" hint is intentionally absent).
  await expect(page.getByTestId('catalog-instock-only')).toBeVisible();
});

test('on a phone the list becomes cards and the catalog is full screen', async ({ page, request }) => {
  const { jobId } = await seedGraph(page, request);
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();

  await expect(page.getByTestId('workspace-table')).toHaveCount(0);
  await expect(page.getByText('Lead mic').first()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);

  await page.getByTestId('open-catalog').click();
  const box = await page.getByTestId('catalog-search').boundingBox();
  expect(box && box.x >= 0 && box.x + box.width <= 390).toBe(true);
});

async function seedPair(page: Page, request: APIRequestContext) {
  await enableStockwire(request);
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Connect ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const mic = await post(request, headers, `${g}/devices`, {
    domain: 'audio',
    name: 'Lead mic',
    canvas_x_cm: 100,
    canvas_y_cm: 100,
    ports: [{ id: 'out', direction: 'out', signal: 'audio', connector: 'xlr3' }],
  });
  const box = await post(request, headers, `${g}/devices`, {
    domain: 'audio',
    name: 'Stagebox',
    canvas_x_cm: 500,
    canvas_y_cm: 100,
    ports: [{ id: 'in', direction: 'in', signal: 'audio', connector: 'xlr3', channels: 32 }],
  });
  return { jobId, headers, mic, box };
}

const graphOf = async (request: APIRequestContext, headers: Record<string, string>, jobId: string) =>
  (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })).json();

test('dragging from one device to another with the connect tool creates a connection', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  const { jobId, headers } = await seedPair(page, request);
  await page.goto(`/jobs/${jobId}/workspace`);
  const canvas = page.getByTestId('workspace-canvas');
  await expect(canvas).toBeVisible();

  await page.getByTestId('connect-tool').click();
  const box = (await canvas.boundingBox())!;
  const zoom = await fittedZoom(page);
  // each device box is 96x40 px with its top-left at (cm * zoom)
  const from = { x: box.x + 100 * zoom + 48, y: box.y + 100 * zoom + 20 };
  const to = { x: box.x + 500 * zoom + 48, y: box.y + 100 * zoom + 20 };
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move((from.x + to.x) / 2, from.y, { steps: 5 });
  await page.mouse.move(to.x, to.y, { steps: 5 });
  await page.mouse.up();

  await expect
    .poll(async () => (await graphOf(request, headers, jobId)).edges.length)
    .toBe(1);
  const edge = (await graphOf(request, headers, jobId)).edges[0];
  expect(edge).toMatchObject({ signal: 'audio', src_port: 'out', dst_port: 'in' });
});

test('catalog items can be dragged onto the canvas and cases are picked from a list', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  const { jobId, headers } = await seedPair(page, request);
  await page.route('**/api/v1/stockwire/catalog/search*', (route) =>
    route.fulfill({
      json: {
        items: [
          { id: 7, name: 'Dragged Spot', category: 'Moving lights', manufacturer: 'Elation', available_qty: 3, booked: false, booked_qty: 0 },
        ],
        total: 1,
        facets: { category: { 'Moving lights': 1 }, manufacturer: { Elation: 1 } },
        availability: { date_range_supported: false },
      },
    }),
  );
  await page.route('**/api/v1/stockwire/catalog/cases', (route) =>
    route.fulfill({ json: { items: [{ id: 55, name: 'Rack case', asset_tag: 'C-55', child_count: 2 }] } }),
  );
  await page.route('**/api/v1/stockwire/catalog/cases/55/children', (route) =>
    route.fulfill({
      json: {
        items: [
          { id: 551, product: { id: 1, name: 'Receiver A', category: 'Wireless audio' } },
          { id: 552, product: { id: 1, name: 'Receiver B', category: 'Wireless audio' } },
        ],
      },
    }),
  );
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('open-catalog').click();
  await expect(page.getByTestId('catalog-item')).toHaveCount(1);

  const canvas = page.getByTestId('workspace-canvas');
  await page.getByTestId('catalog-item').dragTo(canvas, { targetPosition: { x: 400, y: 300 } });
  await expect
    .poll(async () => (await graphOf(request, headers, jobId)).devices.map((d: { name: string }) => d.name))
    .toContain('Dragged Spot');
  const dropped = (await graphOf(request, headers, jobId)).devices.find(
    (d: { name: string }) => d.name === 'Dragged Spot',
  );
  expect(dropped).toMatchObject({ domain: 'lighting', stockwire_product_id: '7' });
  // drop point (400, 300) px at the canvas zoom, relative to the stage and snapped to the 10 cm grid
  const zoom = await fittedZoom(page);
  expect(Math.abs(dropped.canvas_x_cm - 400 / zoom)).toBeLessThanOrEqual(10);
  expect(Math.abs(dropped.canvas_y_cm - 300 / zoom)).toBeLessThanOrEqual(10);

  await page.getByText(/add a case with its contents|lägg till en case med innehåll/i).click();
  await page.getByTestId('case-select').click();
  await page.getByRole('option', { name: /rack case/i }).click();
  await page.getByRole('button', { name: /add case and contents|lägg till case/i }).click();
  await expect
    .poll(async () => (await graphOf(request, headers, jobId)).devices.filter((d: { case_parent_id: string | null }) => d.case_parent_id).length)
    .toBe(2);
});

test('the phase chips use the rating of the power sources', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Phase ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const source = await post(request, headers, `${g}/devices`, {
    domain: 'power',
    kind: 'source',
    name: 'Mains',
    attributes: { rating_amps: 32 },
    ports: [{ id: 'out', direction: 'out', signal: 'power', max_connections: 4 }],
  });
  const load = await post(request, headers, `${g}/devices`, {
    domain: 'lighting',
    name: 'Wash',
    attributes: { power_w: 6000 },
    ports: [{ id: 'in', direction: 'in', signal: 'power' }],
  });
  await post(request, headers, `${g}/edges`, {
    signal: 'power',
    src_device_id: source.id,
    src_port: 'out',
    dst_device_id: load.id,
    dst_port: 'in',
    phase: 'L1',
  });
  await page.goto(`/jobs/${jobId}/workspace`);
  const chip = page.getByTestId('phase-L1');
  await expect(chip).toContainText('6000 W');
  await expect(chip).toHaveClass(/bg-warning/);
});

test('a channel list can be exported from the graph', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Export ${Date.now()}` })).id as string;
  const lst = await post(request, headers, `/jobs/${jobId}/channel-lists`, { name: 'FOH Inputs' });
  await post(request, headers, `/jobs/${jobId}/channel-lists/${lst.id}/channels`, {
    channel_number: 1,
    source_label: 'Kick',
  });
  await post(request, headers, `/jobs/${jobId}/graph/backfill`, {});
  await page.goto(`/jobs/${jobId}/workspace`);

  await page.getByTestId('export-menu').click();
  const download = page.waitForEvent('download');
  await page.getByTestId('export-generic_csv').click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.zip$/);
});

test('renaming a channel in the sound editor updates the channel list, and the canvas ignores channels', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Round trip ${Date.now()}` })).id as string;
  const lst = await post(request, headers, `/jobs/${jobId}/channel-lists`, { name: 'FOH Inputs' });
  const channel = await post(request, headers, `/jobs/${jobId}/channel-lists/${lst.id}/channels`, {
    channel_number: 1,
    source_label: 'Kick',
  });

  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();
  const row = page.getByTestId('channel-table').locator('tbody tr').filter({ has: page.locator('input') }).first();
  await expect(row.getByTestId('channel-label')).toHaveValue('Kick');
  await row.getByTestId('channel-label').fill('Kick In');
  await row.getByTestId('channel-label').press('Enter');

  await expect
    .poll(async () => {
      const rows = await (
        await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists/${lst.id}/channels`, { headers })
      ).json();
      return rows.find((r: { id: string }) => r.id === channel.id)?.source_label;
    })
    .toBe('Kick In');

  await page.getByTestId('mode-toggle').getByText(/stage plot|scenplan/i).click();
  await page.waitForTimeout(500);
  const graph = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })).json();
  const node = graph.devices.find((d: { kind: string }) => d.kind === 'channel');
  expect(node.canvas_x_cm).toBeNull();
});

test('plot elements are drawn on the workspace canvas: dragging moves the element, connecting links it', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Elements ${Date.now()}` })).id as string;
  const element = await post(request, headers, `/jobs/${jobId}/plot-elements`, {
    element_type: 'microphone',
    label: 'Vox mic',
    position_x: 100,
    position_y: 100,
    width_cm: 100,
    height_cm: 50,
  });
  const box = await post(request, headers, `/jobs/${jobId}/devices`, {
    name: 'Stagebox',
    device_type: 'analog_stagebox',
  });
  const graphOf = async () => (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })).json();
  const boxNode = (await graphOf()).devices.find((d: { name: string }) => d.name === 'Stagebox');
  await request.patch(`${API_BASE}/api/v1/jobs/${jobId}/graph/devices/${boxNode.id}`, {
    headers,
    data: { canvas_x_cm: 600, canvas_y_cm: 100, expected_revision: boxNode.revision },
  });

  await page.goto(`/jobs/${jobId}/workspace`);
  const canvas = page.getByTestId('workspace-canvas');
  await expect(canvas).toBeVisible();
  const area = (await canvas.boundingBox())!;
  const zoom = await fittedZoom(page);
  // element: top-left (100,100) cm, 100x50 cm -> 80x40 px; grab it near its middle
  const grab = { x: area.x + 100 * zoom + 40, y: area.y + 100 * zoom + 20 };
  await page.mouse.move(grab.x, grab.y);
  await page.mouse.down();
  await page.mouse.move(grab.x + 60, grab.y + 40, { steps: 6 });
  await page.mouse.up();

  await expect
    .poll(async () => {
      const rows = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, { headers })).json();
      return Math.round(rows.find((r: { id: string }) => r.id === element.id).position_x);
    })
    .toBe(Math.round(100 + 60 / zoom));

  await page.getByTestId('connect-tool').click();
  const movedX = 100 + 60 / zoom;
  const movedY = 100 + 40 / zoom;
  const from = { x: area.x + movedX * zoom + 40, y: area.y + movedY * zoom + 20 };
  const to = { x: area.x + 600 * zoom + 48, y: area.y + 100 * zoom + 20 };
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 8 });
  await page.mouse.up();

  await expect
    .poll(async () => {
      const rows = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, { headers })).json();
      return rows.find((r: { id: string }) => r.id === element.id).linked_device_id;
    })
    .toBe(box.id);
});

test('a channel list is built in the channel list editor and ends up in the exports', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Lists ${Date.now()}` })).id as string;
  const box = await post(request, headers, `/jobs/${jobId}/graph/devices`, { domain: 'audio', name: 'Stagebox A' });
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();

  await page.getByTestId('add-list').click();
  await expect(page.getByTestId('list-tab')).toHaveCount(1);
  await page.getByTestId('add-channel').click();
  const row = page.getByTestId('channel-table').locator('tbody tr').filter({ has: page.locator('input') }).first();
  await row.getByTestId('channel-label').fill('Kick');
  await row.getByTestId('channel-label').press('Enter');

  await row.getByTestId('edit-chain').click();
  await page.getByTestId('chain-add-step').click();
  await page.getByTestId('chain-device').first().click();
  await page.locator('.q-menu .q-item', { hasText: 'Stagebox A' }).click();
  await page.getByTestId('chain-save').click();
  await expect(row.getByTestId('edit-chain')).toContainText('Stagebox A');

  // the chain is also shown as a signal flow diagram, with a way back to editing it
  await row.getByTestId('show-flow').click();
  await expect(page.getByTestId('chain-flow')).toContainText('Kick');
  await expect(page.getByTestId('chain-flow')).toContainText('Stagebox A');
  await page.getByTestId('flow-edit-chain').click();
  await expect(page.getByTestId('chain-save')).toBeVisible();
  await page.getByTestId('chain-save').click();

  await expect
    .poll(async () => {
      const lists = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json();
      const ch = lists[0]?.channels?.[0];
      return ch && [ch.source_label, ch.patch_points.length];
    })
    .toEqual(['Kick', 1]);
  expect(box.id).toBeTruthy();

  await page.getByTestId('add-output').click();
  await expect(page.getByTestId('output-row')).toHaveCount(1);
});

test('a device is created and edited in the device editor, with ports and camera specs', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Devices ${Date.now()}` })).id as string;
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(devices|enheter)$/i).click();

  await page.getByTestId('new-device').click();
  await page.getByTestId('device-name').fill('PTZ 1');
  await page.getByTestId('device-type').click();
  await page.locator('.q-menu .q-item', { hasText: /^PTZ camera$/ }).click();
  await page.getByTestId('connector-preset').filter({ hasText: /SDI in$/ }).click();
  await page.getByTestId('connector-preset').filter({ hasText: /SDI in$/ }).click();
  await page.getByTestId('connector-preset').filter({ hasText: /Dante$/ }).click();
  await page.getByTestId('add-port').click();
  await page.getByTestId('port-direction').last().click();
  await page.locator('.q-menu .q-item', { hasText: /^Out$/ }).click();
  await page.getByTestId('port-connector').last().click();
  await page.getByTestId('port-connector').last().fill('speakon');
  await page.keyboard.press('Enter');
  await page.getByLabel(/sensor width/i).fill('9.6');
  await page.getByTestId('device-save').click();

  const legacy = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json())[0];
  await expect.poll(async () => (await legacy())?.device_type).toBe('ptz_camera');
  const created = await legacy();
  expect(created.sensor_width_mm).toBe(9.6);
  // the same preset twice raises the count, a bidirectional connector is stored as an in and an out
  expect(created.ports).toEqual(
    expect.arrayContaining([
      { direction: 'in', connector: 'sdi', count: 2 },
      { direction: 'in', connector: 'dante', count: 1 },
      { direction: 'out', connector: 'dante', count: 1 },
      { direction: 'out', connector: 'speakon', count: 1 },
    ]),
  );
  expect(created.ports).toHaveLength(4);

  await expect(page.getByTestId('device-table').locator('tbody input').first()).toHaveValue('PTZ 1');
  await page.getByTestId('edit-device').click();
  await page.getByLabel(/max.*distance/i).fill('40');
  await page.getByTestId('device-save').click();
  await expect.poll(async () => (await legacy()).max_distance_m).toBe(40);
});

test('fixtures are patched in the lights editor and DMX overlaps are flagged', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Lights ${Date.now()}` })).id as string;
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(lights|ljus)$/i).click();

  await page.getByTestId('add-fixture').click();
  await expect(page.getByTestId('fixture-table').locator('tbody tr').filter({ has: page.locator('input') })).toHaveCount(1);
  await page.getByTestId('add-fixture').click();
  const rows = page.getByTestId('fixture-table').locator('tbody tr').filter({ has: page.locator('input') });
  await expect(rows).toHaveCount(2);
  await expect(page.getByTestId('dmx-conflict')).toHaveCount(0);

  const legacy = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/fixtures`, { headers })).json()) as {
      dmx_address: number;
      dmx_conflict: boolean;
    }[];
  await expect.poll(async () => (await legacy()).map((f) => f.dmx_address).sort()).toEqual([1, 2]);

  // footprints of 4 on addresses 1 and 2 overlap
  for (const [index, footprint] of [[0, '4'], [1, '4']] as const) {
    const field = rows.nth(index).getByTestId('fixture-footprint');
    await field.fill(footprint);
    await field.press('Enter');
  }
  await expect(page.getByTestId('dmx-conflict')).toHaveCount(2);
  await expect.poll(async () => (await legacy()).every((f) => f.dmx_conflict)).toBe(true);

  const address = rows.nth(1).getByTestId('fixture-dmx_address');
  await address.fill('20');
  await address.press('Enter');
  await expect(page.getByTestId('dmx-conflict')).toHaveCount(0);
});

test('a DMX universe is built in the lights editor with a source, a chain and an imported fixture', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E DMX ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/graph/audio-devices`, { name: 'Lighting desk', device_type: 'other' });
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(lights|ljus)$/i).click();

  const csv = 'universe,address,type,mode,footprint,location,purpose\n1,1,LED wash,8ch,8,Truss 1,Wash A\n1,9,LED wash,8ch,8,Truss 1,Wash B\n';
  await page.getByTestId('import-file').setInputFiles({ name: 'rig.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
  await expect(page.getByTestId('fixture-table').locator('tbody tr').filter({ has: page.locator('input') })).toHaveCount(2);

  await page.getByTestId('add-universe').click();
  await expect(page.getByTestId('universe-row')).toHaveCount(1);
  await page.getByTestId('universe-source').click();
  await page.locator('.q-menu .q-item', { hasText: 'Lighting desk' }).click();
  await page.getByTestId('edit-universe-chain').click();
  for (let i = 0; i < 2; i += 1) await page.getByTestId('chain-add-step').click();
  const devices = page.getByTestId('chain-device');
  await devices.nth(0).click();
  await page.locator('.q-menu .q-item', { hasText: 'Wash A' }).click();
  await devices.nth(1).click();
  await page.locator('.q-menu .q-item', { hasText: 'Wash B' }).click();
  await page.getByTestId('chain-save').click();

  // the universe is a graph node holding its chain and its source
  const graph = async () => (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })).json()) as any;
  const universe = async () => (await graph()).devices.find((d: any) => d.kind === 'dmx_universe');
  await expect.poll(async () => (await universe())?.attributes?.steps?.length).toBe(2);
  const desk = (await graph()).devices.find((d: any) => d.name === 'Lighting desk');
  expect((await universe()).attributes.source_device_id).toBe(desk.id);
  await page.getByText(/flow diagram|flödesdiagram/i).click();
  await expect(page.getByText('Wash B').first()).toBeVisible();
});

test('the fixture library is managed in the lights editor and its modes set the footprint', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Library ${Date.now()}` })).id as string;
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(lights|ljus)$/i).click();

  await page.getByTestId('open-library').click();
  await page.getByTestId('library-type-name').fill('LED wash');
  await page.getByTestId('library-add-type').click();
  await page.getByTestId('library-type').first().click();
  for (const [name, footprint] of [['16ch', '16'], ['8ch', '8']]) {
    await page.getByTestId('library-mode-name').fill(name);
    await page.getByTestId('library-mode-footprint').fill(footprint);
    await page.getByTestId('library-add-mode').click();
    await expect(page.getByTestId('library-mode').filter({ has: page.locator(`input[value="${name}"]`) })).toHaveCount(1);
  }
  await page.keyboard.press('Escape');

  await page.getByTestId('add-fixture').click();
  const row = page.getByTestId('fixture-table').locator('tbody tr').filter({ has: page.locator('input') }).first();
  await row.getByTestId('fixture-fixture_type').click();
  await page.locator('.q-menu .q-item', { hasText: 'LED wash' }).click();
  await expect
    .poll(async () => (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/fixtures`, { headers })).json())[0]?.fixture_type)
    .toBe('LED wash');
  await row.getByTestId('fixture-channel_mode').click();
  await page.locator('.q-menu .q-item', { hasText: '16ch' }).click();

  const legacy = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/fixtures`, { headers })).json())[0];
  await expect.poll(async () => (await legacy())?.footprint).toBe(16);
  expect((await legacy()).fixture_type).toBe('LED wash');
  await expect(row.getByTestId('fixture-footprint')).toHaveValue('16');
});

test('a fixture type is imported from Stockwire into the library', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await enableStockwire(request);
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Import ${Date.now()}` })).id as string;
  await page.route('**/api/v1/stockwire/products*', (route) =>
    route.fulfill({ json: { items: [{ id: 91, name: 'Wash Pro 300', sku: 'WP300', manufacturer: 'Acme', category: 'Lights' }], total: 1 } }),
  );
  let imported: { product_id?: string } | null = null;
  await page.route(`**/api/v1/jobs/${jobId}/fixture-types/from-stockwire`, (route) => {
    imported = route.request().postDataJSON();
    return route.fulfill({
      status: 201,
      json: { id: '00000000-0000-0000-0000-000000000001', job_id: jobId, name: 'Wash Pro 300', manufacturer: 'Acme', source: 'stockwire', modes: [] },
    });
  });
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(lights|ljus)$/i).click();
  await page.getByTestId('open-library').click();
  await page.getByLabel(/add type from stockwire|lägg till typ från stockwire/i).fill('wash');
  await page.locator('.q-menu .q-item', { hasText: 'Wash Pro 300' }).click();
  await expect.poll(() => imported?.product_id).toBe('91');
  await expect(page.getByText(/added wash pro 300|lade till wash pro 300/i)).toBeVisible();
});

test('a video list is built in the video editor: inputs, outputs and a patch chain', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Video ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/graph/audio-devices`, { name: 'Switcher A', device_type: 'switcher' });
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^video$/i).click();

  await page.getByTestId('add-video-list').click();
  await expect(page.getByTestId('video-list-tab')).toHaveCount(1);
  await page.getByTestId('add-video-input').click();
  const row = page.getByTestId('video-video_input-table').locator('tbody tr').filter({ has: page.locator('input') }).first();
  await row.getByTestId('video-name').fill('Cam 1');
  await row.getByTestId('video-name').press('Enter');

  await row.getByTestId('edit-video-chain').click();
  await page.getByTestId('chain-add-step').click();
  await page.getByTestId('chain-device').first().click();
  await page.locator('.q-menu .q-item', { hasText: 'Switcher A' }).click();
  // the connector field offers the shared list; a name that is not in it is added to the list
  await page.getByTestId('chain-connector').click();
  const kind = `Neon plug ${String(Date.now()).slice(-5)}`;
  await page.keyboard.type(kind);
  await page.keyboard.press('Enter');
  await page.getByTestId('chain-save').click();
  await expect(row.getByTestId('edit-video-chain')).toContainText('Switcher A');
  await row.getByTestId('show-video-flow').click();
  await expect(page.getByTestId('chain-flow')).toContainText('Switcher A');
  await page.keyboard.press('Escape');

  const legacy = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/video-lists`, { headers })).json()) as {
      inputs: { source_label: string; patch_points: { connector: string }[] }[];
      outputs: unknown[];
    }[];
  await expect
    .poll(async () => {
      const input = (await legacy())[0]?.inputs[0];
      return input && [input.source_label, input.patch_points[0]?.connector];
    })
    .toEqual(['Cam 1', kind.toLowerCase().replace(/ /g, '-')]);
  const kinds = (await (await request.get(`${API_BASE}/api/v1/connector-kinds`, { headers })).json()) as { label: string }[];
  expect(kinds.map((k) => k.label)).toContain(kind);

  await page.getByTestId('add-video-output').click();
  await expect(page.getByTestId('video-video_output-table').locator('tbody tr').filter({ has: page.locator('input') })).toHaveCount(1);
  await expect.poll(async () => (await legacy())[0]?.outputs.length).toBe(1);
});

test('rigging points and the power tree are built in the rigging editor and fixtures hang and plug in', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Power ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  await post(request, headers, `${g}/fixtures`, { purpose: 'Wash 1', footprint: 8 });
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/rigging & power|rigg & ström/i).click();

  await page.getByTestId('add-truss').click();
  await expect(page.getByTestId('truss-card')).toHaveCount(1);
  await page.getByTestId('truss-capacity').fill('250');
  await page.getByTestId('truss-capacity').press('Enter');

  await page.getByTestId('add-power-node').click();
  await page.getByTestId('new-power-name').fill('Mains');
  await page.getByTestId('new-power-feed').click();
  await page.locator('.q-menu .q-item', { hasText: /63 A, 3-phase/ }).click();
  await page.getByTestId('add-output-row').click();
  await page.getByTestId('output-connector').click();
  await page.locator('.q-menu .q-item', { hasText: /^Schuko 16 A$/ }).click();
  await page.getByTestId('create-power-save').click();
  await expect(page.getByTestId('power-node')).toHaveCount(1);

  const legacy = async (path: string) =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/${path}`, { headers })).json()) as any[];
  await expect.poll(async () => (await legacy('rigging-points'))[0]?.weight_capacity_kg).toBe(250);
  await expect.poll(async () => (await legacy('power-nodes'))[0]?.name).toBe('Mains');

  const row = page.getByTestId('load-row').first();
  await row.getByTestId('load-point').click();
  await page.locator('.q-menu .q-item').first().click();
  await row.getByTestId('load-node').click();
  await page.locator('.q-menu .q-item', { hasText: 'Mains' }).click();
  await expect
    .poll(async () => {
      const fx = (await legacy('fixtures'))[0];
      return fx && [fx.rigging_point_id !== null, fx.power_node_id !== null, fx.power_connector];
    })
    .toEqual([true, true, 'schuko']);
});

test('fixtures are added in bulk by kind and quantity, and the header offers import, export and PDF reports', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await enableStockwire(request);
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Bulk ${Date.now()}` })).id as string;
  await page.goto(`/jobs/${jobId}/workspace`);

  await expect(page.getByTestId('open-catalog')).toBeVisible();
  await expect(page.getByTestId('import-menu')).toBeVisible();
  await expect(page.getByTestId('open-reports')).toBeVisible();
  await page.getByTestId('open-reports').click();
  await expect(page.locator('.q-dialog')).toBeVisible();
  await page.keyboard.press('Escape');

  await page.getByTestId('mode-toggle').getByText(/^lights$|^ljus$/i).click();
  await page.getByTestId('bulk-fixtures').click();
  await page.getByTestId('bulk-type').first().click();
  await page.keyboard.type('Wash');
  await page.keyboard.press('Enter');
  await page.getByTestId('bulk-footprint').first().fill('16');
  await page.getByTestId('bulk-quantity').first().fill('3');
  await page.getByTestId('bulk-add-kind').click();
  await page.getByTestId('bulk-type').nth(1).click();
  await page.keyboard.type('Spot');
  await page.keyboard.press('Enter');
  await page.getByTestId('bulk-footprint').nth(1).fill('40');
  await page.getByTestId('bulk-quantity').nth(1).fill('2');
  await page.getByTestId('bulk-start').fill('1');
  await expect(page.getByTestId('bulk-total')).toContainText('5');
  await page.getByTestId('bulk-create').click();

  const legacy = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/fixtures`, { headers })).json()) as {
      dmx_address: number;
      universe: number;
      fixture_type: string;
    }[];
  await expect.poll(async () => (await legacy()).map((f) => [f.fixture_type, f.universe, f.dmx_address])).toEqual([
    ['Wash', 1, 1],
    ['Wash', 1, 17],
    ['Wash', 1, 33],
    ['Spot', 1, 49],
    ['Spot', 1, 89],
  ]);
});

test('the power flow takes extension cords, editable breakouts, outlets as sources and plugged devices', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Power flow ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const source = await post(request, headers, `${g}/power-nodes`, {
    name: 'Mains',
    kind: 'source',
    feed_connector: 'cee63_3p',
    rating_amps: 63,
    outputs: [{ connector: 'cee32_3p', count: 1 }],
  });
  await post(request, headers, `${g}/power-nodes`, {
    name: 'Breakout',
    kind: 'breakout',
    parent_id: source.id,
    feed_connector: 'cee32_3p',
    outputs: [{ connector: 'schuko', count: 4 }],
  });
  await post(request, headers, `${g}/audio-devices`, { name: 'Amp', device_type: 'other', power_watts: 600 });
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/rigging & power|rigg & ström/i).click();
  await expect(page.getByTestId('power-node')).toHaveCount(2);

  // edit the breakout after creation
  await page.getByTestId('power-node').filter({ hasText: 'Breakout' }).getByTestId('power-edit').click();
  await page.getByTestId('edit-power-name').fill('Breakout FOH');
  await page.getByTestId('edit-power-save').click();
  const legacy = async (path: string) =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/${path}`, { headers })).json()) as any[];
  await expect.poll(async () => (await legacy('power-nodes')).map((n) => n.name).sort()).toEqual(['Breakout FOH', 'Mains']);

  // a skarvsladd goes between the breakout and what feeds it
  await page.getByTestId('power-node').filter({ hasText: 'Breakout' }).getByTestId('power-add-extension').click();
  await page.getByTestId('ext-length').fill('10');
  await page.getByTestId('ext-save').click();
  await expect(page.getByTestId('power-node')).toHaveCount(3);
  await expect(page.getByTestId('power-node').filter({ hasText: /10 m/ })).toHaveCount(1);
  await expect
    .poll(async () => {
      const nodes = await legacy('power-nodes');
      const cord = nodes.find((n) => n.kind === 'extension');
      const breakout = nodes.find((n) => n.name === 'Breakout FOH');
      return cord && breakout && breakout.parent_id === cord.id;
    })
    .toBe(true);

  // the unplugged device is plugged into the breakout in one go
  await expect(page.getByTestId('plug-all')).toContainText('1');
  await page.getByTestId('plug-all-node').click();
  await page.locator('.q-menu .q-item', { hasText: 'Breakout FOH' }).click();
  await page.getByTestId('plug-all-go').click();
  await expect(page.getByTestId('plug-all')).toHaveCount(0);
});

test('the stage and venue are edited on the canvas, plot objects are added and a performer is linked to a channel', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Plot ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const list = await post(request, headers, `${g}/lists`, { name: 'FOH' });
  await post(request, headers, `${g}/lists/${list.id}/channels`, { source_label: 'Lead vocal' });
  await page.goto(`/jobs/${jobId}/workspace`);

  await page.getByTestId('edit-stage-venue').click();
  await page.getByTestId('stage-width').fill('12');
  await page.getByTestId('venue-width').fill('20');
  await page.getByTestId('venue-height').fill('15');
  await page.getByTestId('stage-venue-save').click();
  const job = async () => (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}`, { headers })).json()) as Record<string, number>;
  await expect.poll(async () => [(await job()).stage_width_cm, (await job()).venue_width_cm, (await job()).venue_height_cm]).toEqual([1200, 2000, 1500]);

  await page.getByTestId('add-object').click();
  await page.getByTestId('add-object-performer').click();
  const elements = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, { headers })).json()) as {
      element_type: string;
      linked_channel_id: string | null;
      width_cm: number;
    }[];
  await expect.poll(async () => (await elements()).map((e) => e.element_type)).toEqual(['performer']);
  await expect(page.getByTestId('element-inspector')).toBeVisible();

  await page.getByTestId('element-channel').click();
  await page.locator('.q-menu .q-item', { hasText: 'Lead vocal' }).click();
  await expect.poll(async () => (await elements())[0]?.linked_channel_id).not.toBeNull();

  // gear size is set per device and as a whole
  await page.getByTestId('inspector-width').fill('120');
  await page.getByTestId('inspector-width').press('Enter');
  await expect.poll(async () => (await elements())[0]?.width_cm).toBe(120);

  const specs = page.waitForResponse((res) => res.url().includes('/camera-specs'));
  await page.getByTestId('layer-camera').click();
  await specs;
  await page.getByTestId('layer-projector').click();
  await page.getByTestId('layer-coverage').click();
});

test('a device is created from a Stockwire product with its connectors and power inlet', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await enableStockwire(request);
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Product import ${Date.now()}` })).id as string;
  await page.route('**/api/v1/stockwire/products?*', (route) =>
    route.fulfill({ json: { items: [{ id: 55, name: 'Stage box 32', sku: 'SB32', category: 'Audio' }], total: 1 } }),
  );
  await page.route('**/api/v1/stockwire/products/55/device-specs', (route) =>
    route.fulfill({
      json: {
        id: 55,
        name: 'Stage box 32',
        connector_groups: [
          { connector: 'xlr3', direction: 'in', count: 32, signal: 'audio' },
          { connector: 'dante', direction: 'both', count: 1, signal: null },
        ],
        power_inlet: 'iec_c13',
        weight_kg: 14,
        power_watts: 60,
      },
    }),
  );
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^devices$|^enheter$/i).click();
  await page.getByTestId('new-device').click();
  await page.getByTestId('device-from-stockwire').click();
  await page.keyboard.type('stage');
  await page.locator('.q-menu .q-item', { hasText: 'Stage box 32' }).click();
  await expect(page.getByTestId('device-name')).toHaveValue('Stage box 32');
  await expect(page.getByTestId('power-inlet')).toHaveValue('IEC C13');
  await page.getByTestId('device-save').click();

  const legacy = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json()) as {
      name: string;
      weight_kg: number;
      power_inlet: string;
      stockwire_product_id: string;
      ports: { direction: string; connector: string; count: number }[];
    }[];
  await expect.poll(async () => (await legacy())[0]?.stockwire_product_id).toBe('55');
  const device = (await legacy())[0];
  expect([device.weight_kg, device.power_inlet]).toEqual([14, 'iec_c13']);
  expect(device.ports).toEqual(
    expect.arrayContaining([
      { direction: 'in', connector: 'xlr3', count: 32 },
      { direction: 'in', connector: 'dante', count: 1 },
      { direction: 'out', connector: 'dante', count: 1 },
    ]),
  );
});

test('power inlets show in the device list, a new power connector asks for its rating and the power sheet is a report', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Inlets ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/graph/audio-devices`, { name: 'Amp', device_type: 'other', power_watts: 500 });
  await page.goto(`/jobs/${jobId}/workspace`);

  await page.getByTestId('mode-toggle').getByText(/^devices$|^enheter$/i).click();
  await expect(page.getByTestId('device-inlet')).toHaveCount(1);
  await expect(page.getByTestId('device-inlet')).toHaveValue('IEC C13');
  await page.getByTestId('device-inlet').click();
  await page.locator('.q-menu .q-item', { hasText: 'Attached cable, Schuko' }).click();
  await expect
    .poll(async () => ((await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json()) as { power_inlet: string }[])[0]?.power_inlet)
    .toBe('attached_schuko');

  await page.getByTestId('mode-toggle').getByText(/rigging & power|rigg & ström/i).click();
  await page.getByTestId('add-power-node').click();
  const label = `Hubbell ${String(Date.now()).slice(-4)} A`;
  await page.getByTestId('new-power-feed').click();
  await page.keyboard.type(label);
  await page.keyboard.press('Enter');
  await page.locator('input[data-autofocus="true"]').fill('30');
  await page.getByRole('button', { name: 'OK' }).click();
  await expect(page.locator('input[data-autofocus="true"]')).toHaveCount(1);
  await expect(page.locator('input[data-autofocus="true"]')).toHaveValue('1');
  await page.locator('input[data-autofocus="true"]').fill('1');
  await page.getByRole('button', { name: 'OK' }).click();
  const kinds = async () =>
    (await (await request.get(`${API_BASE}/api/v1/connector-kinds`, { headers })).json()) as {
      label: string;
      power: boolean;
      amps: number;
      phases: number;
    }[];
  await expect.poll(async () => (await kinds()).find((k) => k.label === label)).toMatchObject({ power: true, amps: 30, phases: 1 });

  await page.keyboard.press('Escape');
  await page.getByTestId('open-reports').click();
  await page.getByRole('combobox', { name: /^template$|^mall$/i }).click();
  await expect(page.locator('.q-menu .q-item', { hasText: /power & cables|ström och kablar/i })).toBeVisible();
});

test('the map fits the page width and the page scrolls; zoomed in, the hand tool and Space pan it', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (
    await post(request, headers, '/jobs', {
      title: `E2E Pan ${Date.now()}`,
      venue_width_cm: 3000,
      venue_height_cm: 4000,
      stage_width_cm: 1000,
      stage_height_cm: 600,
    })
  ).id as string;
  await page.goto(`/jobs/${jobId}/workspace`);
  const canvas = page.getByTestId('workspace-canvas');
  await expect(canvas).toBeVisible();
  await page.getByTestId('canvas-fit').click();

  // fitted: no horizontal scroll, the tall map makes the page itself taller
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const fitted = (await canvas.boundingBox())!;
  expect(fitted.height).toBeGreaterThan(900);
  expect(await canvas.getAttribute('data-pan')).toBe('0,0');

  // zoomed in beyond the fit the map gets its own viewport and the hand tool moves it
  await page.getByLabel('zoom in').click();
  await page.getByLabel('zoom in').click();
  const zoomed = (await canvas.boundingBox())!;
  expect(zoomed.height).toBeLessThan(900);
  await page.getByTestId('hand-tool').click();
  const drag = async () => {
    await page.mouse.move(zoomed.x + 600, zoomed.y + 300);
    await page.mouse.down();
    await page.mouse.move(zoomed.x + 500, zoomed.y + 240, { steps: 5 });
    await page.mouse.up();
  };
  await drag();
  await expect.poll(async () => (await canvas.getAttribute('data-pan'))!.split(',').map(Number)).toEqual([-100, -60]);

  // Space does the same without the tool
  await page.getByTestId('hand-tool').click();
  await page.keyboard.down('Space');
  await page.waitForTimeout(150);
  await drag();
  await page.keyboard.up('Space');
  await expect.poll(async () => (await canvas.getAttribute('data-pan'))!.split(',').map(Number)).toEqual([-200, -120]);
});

test('the sound editor adds channels and outputs in bulk, sets a stand per channel and syncs gear to Stockwire', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  // Enable the integration so the stockwire-dependent sound-editor controls (sync button) are present.
  await enableStockwire(request);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Sound ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/graph/lists`, { name: 'FOH' });
  // the pickers list the company's own equipment, with the number of devices as quantity
  await page.route('**/api/v1/stockwire/own-products*', (route) =>
    route.fulfill({
      json: { items: [{ id: 301, name: 'Boom stand', sku: 'BS1', category: 'Stands', device_count: 12 }], total: 1 },
    }),
  );
  await post(request, headers, `/jobs/${jobId}/graph/audio-devices`, { name: 'Wireless pack A', device_type: 'other' });
  let synced = 0;
  await page.route(`**/api/v1/jobs/${jobId}/sync-stockwire`, (route) => {
    synced += 1;
    return route.fulfill({ json: { added: ['Boom stand'], updated: [], removed: [], errors: [] } });
  });
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();

  await page.getByTestId('bulk-channels').click();
  await page.getByTestId('list-bulk-count').fill('4');
  await page.getByTestId('list-bulk-prefix').fill('Tom');
  await page.getByTestId('list-bulk-create').click();
  const lists = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json()) as {
      channels: { channel_number: number; source_label: string; stand_product_name: string | null }[];
      outputs: { name: string; mode: string }[];
    }[];
  await expect.poll(async () => (await lists())[0]?.channels.map((c) => c.source_label)).toEqual(['Tom 1', 'Tom 2', 'Tom 3', 'Tom 4']);

  await page.getByTestId('bulk-outputs').click();
  await page.getByTestId('list-bulk-count').fill('3');
  await page.getByTestId('list-bulk-prefix').fill('Aux');
  await page.getByTestId('list-bulk-create').click();
  await expect.poll(async () => (await lists())[0]?.outputs.map((o) => o.name)).toEqual(['Aux 1', 'Aux 2', 'Aux 3']);

  const row = page.getByTestId('channel-table').locator('tbody tr').filter({ has: page.locator('input') }).first();
  await row.getByTestId('stand-picker').first().click();
  await page.keyboard.type('boom');
  await expect(page.locator('.q-menu .q-item', { hasText: '×12' })).toBeVisible();
  await page.locator('.q-menu .q-item', { hasText: 'Boom stand' }).click();
  await expect.poll(async () => (await lists())[0]?.channels[0]?.stand_product_name).toBe('Boom stand');

  // the source is picked from what is already in the job (or the own equipment), not typed
  await row.getByTestId('source-picker').first().click();
  await page.keyboard.type('wireless');
  await page.locator('.q-menu .q-item', { hasText: 'Wireless pack A' }).click();
  await expect
    .poll(async () => ((await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json()) as any[])[0]?.channels[0]?.device)
    .toBe('Wireless pack A');

  await page.getByTestId('sync-stockwire').click();
  await expect.poll(() => synced).toBe(1);
  await expect(page.getByText(/1 added|1 tillagda/)).toBeVisible();
});

test('venue power groups and outlets feed the power tree, and gear is plugged into an outlet from the map', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const put = async (path: string, data: object) => {
    const res = await request.put(`${API_BASE}/api/v1${path}`, { headers, data });
    expect(res.status(), `${path}: ${await res.text()}`).toBeLessThan(300);
    return res.json();
  };
  const venue = await post(request, headers, '/venues', { name: `Hall ${Date.now()}` });
  const group = await post(request, headers, `/venues/${venue.id}/power-groups`, { name: 'Stage left', rating_amps: 16, phases: 1 });
  await post(request, headers, `/venues/${venue.id}/power-outlets`, {
    name: 'SL 1',
    connector: 'schuko',
    group_id: group.id,
    x_cm: 600,
    y_cm: 200,
  });
  await post(request, headers, `/venues/${venue.id}/power-outlets`, { name: 'SL 2', connector: 'schuko', group_id: group.id, x_cm: 700, y_cm: 200 });
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Venue power ${Date.now()}` })).id as string;
  await put(`/jobs/${jobId}/venue`, { venue_id: venue.id });
  const amp = await post(request, headers, `/jobs/${jobId}/graph/audio-devices`, { name: 'Amp', device_type: 'other', power_watts: 500 });
  await post(request, headers, `/jobs/${jobId}/graph/audio-devices`, { name: 'Rack', device_type: 'other', power_watts: 200 });
  const graphOf = async () => (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })).json()) as any;
  const ampNode = (await graphOf()).devices.find((d: any) => d.name === 'Amp');
  const patchRes = await request.patch(`${API_BASE}/api/v1/jobs/${jobId}/graph/devices/${ampNode.id}`, {
    headers,
    data: { canvas_x_cm: 300, canvas_y_cm: 200, expected_revision: ampNode.revision },
  });
  expect(patchRes.status()).toBeLessThan(300);

  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('canvas-fit').click();
  const canvas = page.getByTestId('workspace-canvas');
  const box = (await canvas.boundingBox())!;
  const zoom = Number(await canvas.getAttribute('data-zoom'));
  // connect tool: drag from the amp (box 60 x 30 cm at 300,200) to the first outlet (600,200)
  await page.getByTestId('connect-tool').click();
  const from = { x: box.x + (300 + 30) * zoom, y: box.y + (200 + 15) * zoom };
  const to = { x: box.x + 600 * zoom, y: box.y + 200 * zoom };
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move((from.x + to.x) / 2, from.y, { steps: 5 });
  await page.mouse.move(to.x, to.y, { steps: 5 });
  await page.mouse.up();

  await expect
    .poll(async () => {
      const graph = await graphOf();
      const node = graph.devices.find((d: any) => d.name === 'Amp');
      const source = graph.devices.find((d: any) => d.id === node.attributes.power_node_id);
      return source && [source.name, node.attributes.power_connector];
    })
    .toEqual(['Stage left', 'schuko']);
  const nodes = (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/power-nodes`, { headers })).json()) as any[];
  expect(nodes.find((n) => n.name === 'Stage left')).toMatchObject({
    rating_amps: 16,
    outputs: [{ connector: 'schuko', count: 2, phase: 'L1' }],
  });
  // the phase chips show what is plugged in: all of it on the group's one phase
  await expect(page.getByTestId('phase-L1')).toContainText('500');
  await expect(page.getByTestId('phase-L2')).toContainText('0 W');

  // the venue power panel lists the groups and outlets and an outlet can be fed from in the tree
  await page.getByTestId('mode-toggle').getByText(/rigging & power|rigg & ström/i).click();
  await page.getByTestId('venue-power').click();
  await expect(page.getByTestId('venue-group')).toHaveCount(1);
  await expect(page.getByTestId('venue-outlet')).toHaveCount(2);
  await page.getByTestId('add-power-node').click();
  await page.getByTestId('new-power-name').fill('Rack distro');
  await page.getByTestId('new-power-parent').click();
  await expect(page.locator('.q-menu .q-item', { hasText: 'SL 2' })).toBeVisible();
});

test('venue power panel builds a tree of panels, circuits, generators and temporary kit', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const venue = await post(request, headers, '/venues', { name: `Hall ${Date.now()}` });
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Power tree ${Date.now()}` })).id as string;
  await request.put(`${API_BASE}/api/v1/jobs/${jobId}/venue`, { headers, data: { venue_id: venue.id } });

  const groups = async () =>
    (await (await request.get(`${API_BASE}/api/v1/venues/${venue.id}/power-groups`, { headers })).json()) as any[];
  const childOf = (parentKind: string) => async () =>
    (await groups()).some((g) => g.kind === parentKind);

  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/rigging & power|rigg & ström/i).click();
  await page.getByTestId('venue-power').click();

  // No supply yet, so the only offered root is the incoming mains.
  await page.getByTestId('add-venue-incoming').click();
  await expect.poll(childOf('incoming')).toBe(true);

  // A panel nests under the incoming supply by default.
  await page.getByTestId('add-venue-group').click();
  await expect.poll(async () => (await groups()).filter((g) => g.kind === 'panel').length).toBe(1);
  const panel = (await groups()).find((g) => g.kind === 'panel')!;
  const incoming = (await groups()).find((g) => g.kind === 'incoming')!;
  const incomingName = incoming.name;

  // The panel row carries its name in a q-input whose `value` attribute is the name (not visible
  // text), so scope the row by that attribute via a CSS :has() rather than a text filter that misses
  // input values. The parent select is a Quasar q-select whose displayed value lives in the
  // focus-target input's `value` attribute, so assert on that (toHaveValue) instead of innerText(),
  // which is empty for a matched option.
  const panelRow = page.locator(
    `[data-testid="venue-group"]:has(input[data-testid="venue-group-name"][value="${panel.name}"])`,
  );
  const parentSel = panelRow.getByTestId('venue-group-parent');

  // The panel's parent select shows the supply root by its name, never a raw id (the parent field
  // used to fall back to displaying the UUID when the stored value had no matching option).
  await expect(parentSel).not.toHaveValue(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i);
  await expect(parentSel).toHaveValue(incomingName);

  // A fused circuit is added inside the panel (not as a standalone node).
  await panelRow.getByTestId('add-venue-circuit').click();
  await expect
    .poll(async () => {
      const list = await groups();
      const circuit = list.find((g) => g.kind === 'group');
      return circuit && circuit.parent_id === panel.id;
    })
    .toBe(true);

  // A generator is a second supply root (temporary by default) and shows up in the per-source list.
  await page.getByTestId('add-venue-generator').click();
  await expect.poll(async () => {
    const list = await groups();
    const gen = list.find((g) => g.kind === 'generator');
    return gen && gen.temporary === true;
  }).toBe(true);
  await expect(page.getByTestId('venue-supply')).toHaveCount(2);

  // A breakout (temporary distro) is added via its own button and defaults under the incoming supply.
  await page.getByTestId('add-venue-breakout').click();
  await expect
    .poll(async () => {
      const list = await groups();
      const bo = list.find((g) => g.kind === 'breakout');
      const incoming = list.find((g) => g.kind === 'incoming');
      return bo && incoming && bo.parent_id === incoming.id;
    })
    .toBe(true);

  // The outlet group select only offers circuits (kind 'group'), never a panel or supply, and each
  // circuit option is labelled with the board it hangs under so identically-numbered circuits (1-24)
  // stay distinguishable across different panels.
  await page.getByTestId('add-venue-outlet').click();
  const groupSelect = page.getByTestId('venue-outlet-group');
  await groupSelect.click();
  await expect(page.locator('.q-menu .q-item')).toHaveCount(1);
  const circuit = (await groups()).find((g) => g.kind === 'group')!;
  const circuitPanel = (await groups()).find((g) => g.kind === 'panel')!;
  await expect(page.locator('.q-menu .q-item').first()).toContainText(circuitPanel.name);
  await expect(page.locator('.q-menu .q-item').first()).toContainText(circuit.name);
  await page.keyboard.press('Escape');
});

test('an outlet is moved on the map and its position is edited in the venue power panel', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const venue = await post(request, headers, '/venues', { name: `Hall ${Date.now()}` });
  const outlet = await post(request, headers, `/venues/${venue.id}/power-outlets`, { name: 'SL 1', connector: 'schuko', x_cm: 600, y_cm: 200 });
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Outlet ${Date.now()}` })).id as string;
  await request.put(`${API_BASE}/api/v1/jobs/${jobId}/venue`, { headers, data: { venue_id: venue.id } });
  await post(request, headers, `/jobs/${jobId}/graph/audio-devices`, { name: 'Amp', device_type: 'other' });
  const outletRow = async () =>
    ((await (await request.get(`${API_BASE}/api/v1/venues/${venue.id}/power-outlets`, { headers })).json()) as any[]).find((o) => o.id === outlet.id);

  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('canvas-fit').click();
  const canvas = page.getByTestId('workspace-canvas');
  const box = (await canvas.boundingBox())!;
  const zoom = Number(await canvas.getAttribute('data-zoom'));
  const from = { x: box.x + 600 * zoom, y: box.y + 200 * zoom };
  // a click on an outlet marker opens it in the inspector
  await page.mouse.click(from.x, from.y);
  await expect(page.getByTestId('outlet-inspector')).toBeVisible();
  await expect(page.getByTestId('outlet-name')).toHaveValue('SL 1');
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + 50 * zoom, from.y + 40 * zoom, { steps: 6 });
  await page.mouse.up();
  await expect.poll(async () => Math.abs((await outletRow()).x_cm - 650) <= 3 && Math.abs((await outletRow()).y_cm - 240) <= 3).toBe(true);

  await page.getByTestId('mode-toggle').getByText(/rigging & power|rigg & ström/i).click();
  await page.getByTestId('venue-power').click();
  await page.getByTestId('venue-outlet-x').fill('300');
  await page.getByTestId('venue-outlet-x').press('Enter');
  await expect.poll(async () => (await outletRow()).x_cm).toBe(300);
});

test('the job details and the Stockwire link are edited in the workspace, and the stage and venue are in metres', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  // Enable the integration so the job details Stockwire-link controls are present.
  await enableStockwire(request);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Job ${Date.now()}` })).id as string;
  let linkedBody: { stockwire_job_id: string | null } | null = null;
  await page.route('**/api/v1/stockwire/rental-jobs*', (route) =>
    route.fulfill({ json: { items: [{ id: 4711, name: 'Summer festival', venue_name: 'Park' }] } }),
  );
  await page.route(`**/api/v1/stockwire/jobs/${jobId}/link`, (route) => {
    linkedBody = route.request().postDataJSON();
    return route.fulfill({ json: { stockwire_job_id: '4711' } });
  });
  await page.goto(`/jobs/${jobId}/workspace`);

  await page.getByTestId('open-job-details').click();
  await page.getByTestId('job-title').fill('Renamed show');
  await page.getByTestId('job-link-existing').click();
  await page.getByTestId('job-link-result').filter({ hasText: 'Summer festival' }).click();
  await expect.poll(() => linkedBody?.stockwire_job_id).toBe('4711');
  await page.getByTestId('job-save').click();
  await expect
    .poll(async () => ((await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}`, { headers })).json()) as { title: string }).title)
    .toBe('Renamed show');
  await expect(page.getByTestId('job-summary')).toContainText('Renamed show');

  await page.getByTestId('edit-stage-venue').click();
  await expect(page.getByLabel(/stage width \(m\)|scenbredd \(m\)/i)).toBeVisible();
  await expect(page.getByLabel(/venue width \(m\)|lokalbredd \(m\)/i)).toBeVisible();
});

test('bus channels are set on an output chain and a plugged device is unplugged from the inspector', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Bus ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const list = await post(request, headers, `${g}/lists`, { name: 'FOH' });
  await post(request, headers, `${g}/lists/${list.id}/outputs`, { name: 'Main', mode: 'lcr_sub' });
  await post(request, headers, `${g}/audio-devices`, { name: 'Sub amp', device_type: 'other', power_watts: 900 });
  const source = await post(request, headers, `${g}/power-nodes`, {
    name: 'Mains',
    kind: 'source',
    feed_connector: 'cee63_3p',
    rating_amps: 63,
    outputs: [{ connector: 'schuko', count: 2 }],
  });
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();
  await page.getByTestId('output-row').getByRole('button', { name: /edit patch|redigera patch/i }).click();
  await page.getByTestId('chain-add-step').click();
  await page.getByTestId('chain-device').first().click();
  await page.locator('.q-menu .q-item', { hasText: 'Sub amp' }).click();
  await page.getByTestId('chain-bus-channel').click();
  await page.locator('.q-menu .q-item', { hasText: /^Sub$/ }).click();
  await page.getByTestId('chain-save').click();
  const lists = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json()) as {
      outputs: { points: { bus_connector: string | null }[] }[];
    }[];
  await expect.poll(async () => (await lists())[0]?.outputs[0]?.points[0]?.bus_connector).toBe('Sub');

  const graphOf = async () => (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })).json()) as any;
  const amp = (await graphOf()).devices.find((d: any) => d.name === 'Sub amp');
  const res = await request.put(`${API_BASE}/api/v1/jobs/${jobId}/graph/loads/${amp.id}`, {
    headers,
    data: { power_node_id: source.id, power_connector: 'schuko' },
  });
  expect(res.status()).toBeLessThan(300);
  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();
  const rows = page.getByTestId('workspace-table').locator('tbody tr').filter({ has: page.locator('input') });
  for (let i = 0; i < (await rows.count()); i += 1) {
    await rows.nth(i).locator('td').nth(1).click();
    if ((await page.getByTestId('inspector-name').inputValue()) === 'Sub amp') break;
  }
  await expect(page.getByTestId('plugged-into').first()).toContainText('Mains');
  await page.getByTestId('unplug').first().click();
  await expect
    .poll(async () => (await graphOf()).devices.find((d: any) => d.name === 'Sub amp').attributes.power_node_id ?? null)
    .toBeNull();
});

test('cables are routed on the new map: settings, a drawn cableway and the cable list', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Cables ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const list = await post(request, headers, `${g}/lists`, { name: 'FOH' });
  const channel = await post(request, headers, `${g}/lists/${list.id}/channels`, { source_label: 'Kick' });
  const box = await post(request, headers, `${g}/audio-devices`, { name: 'Stagebox', device_type: 'analog_stagebox' });
  const desk = await post(request, headers, `${g}/audio-devices`, { name: 'Desk', device_type: 'mixer' });
  const chain = await request.put(`${API_BASE}/api/v1${g}/channels/${channel.id}/chain`, {
    headers,
    data: { steps: [{ device_id: box.id }, { device_id: desk.id }] },
  });
  expect(chain.status()).toBe(200);
  const place = async (node: { id: string; revision: number }, x: number, y: number) => {
    const fresh = ((await (await request.get(`${API_BASE}/api/v1${g}`, { headers })).json()) as any).devices.find((d: any) => d.id === node.id);
    const res = await request.patch(`${API_BASE}/api/v1${g}/devices/${node.id}`, {
      headers,
      data: { canvas_x_cm: x, canvas_y_cm: y, expected_revision: fresh.revision },
    });
    expect(res.status()).toBeLessThan(300);
  };
  await place(box, 200, 100);
  await place(desk, 800, 100);

  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('canvas-fit').click();
  await page.getByTestId('cable-routing').getByText(/^cables$|^kablar$/i).first().click();
  await expect(page.getByTestId('cable-table')).toContainText('Stagebox');
  await expect(page.getByTestId('cable-table')).toContainText('Desk');

  await page.getByTestId('cable-slack-pct').fill('20');
  await page.getByTestId('cable-slack-pct').press('Enter');
  const plan = async () =>
    ((await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}`, { headers })).json()) as any).cable_plan;
  await expect.poll(async () => (await plan()).settings?.slack_pct).toBe(20);

  // a cableway is drawn with two clicks on the map and saved on the job
  const canvas = page.getByTestId('workspace-canvas');
  await page.getByTestId('draw-cableway').click();
  await canvas.scrollIntoViewIfNeeded();
  const area = (await canvas.boundingBox())!;
  const zoom = Number(await canvas.getAttribute('data-zoom'));
  await page.mouse.click(area.x + 200 * zoom, area.y + 170 * zoom);
  await page.mouse.click(area.x + 830 * zoom, area.y + 170 * zoom);
  await page.getByTestId('finish-cableway').click();
  await expect.poll(async () => (await plan()).cableways?.length).toBe(1);
  await expect(page.getByTestId('cableway')).toHaveCount(1);
  await expect(page.getByTestId('cable-table')).toContainText(/10 m|15 m|7.5 m|5 m/);

  // a cable is rerouted by hand: waypoints are clicked on the map and kept in cable_plan.routes
  const routeOf = async () => Object.values(((await plan()).routes || {}) as Record<string, any>)[0];
  await page.getByTestId('cable-reroute').click();
  await expect(page.getByTestId('reroute-bar')).toBeVisible();
  await canvas.scrollIntoViewIfNeeded();
  const area2 = (await canvas.boundingBox())!;
  await page.mouse.click(area2.x + 400 * zoom, area2.y + 300 * zoom);
  await page.mouse.click(area2.x + 600 * zoom, area2.y + 300 * zoom);
  await expect.poll(async () => (await routeOf())?.waypoints?.length).toBe(2);
  expect((await routeOf()).mode).toBe('manual');
  await page.getByTestId('reroute-undo').click();
  await expect.poll(async () => (await routeOf())?.waypoints?.length).toBe(1);
  await page.getByTestId('reroute-done').click();
  await expect(page.getByTestId('reroute-bar')).toBeHidden();

  // hiding takes it off the plot but keeps it in the list; auto route drops the waypoints
  await page.getByTestId('cable-hide').click();
  await expect.poll(async () => (await routeOf())?.hidden).toBe(true);
  await expect(page.getByTestId('cable-table')).toContainText('Stagebox');
  await page.getByTestId('cable-auto-route').click();
  await expect.poll(async () => (await routeOf())?.mode).toBe('auto');
  expect((await routeOf()).waypoints).toEqual([]);
});

test('a patch point can search Stockwire for a device and a video input takes a Stockwire source', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  // Enable the integration so the stockwire "from Stockwire" chain picker is present.
  await enableStockwire(request);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Search ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const vlist = await post(request, headers, `${g}/video-lists`, { name: 'Cameras' });
  await post(request, headers, `${g}/video-lists/${vlist.id}/inputs`, { source_label: '' });
  await page.route('**/api/v1/stockwire/own-products*', (route) =>
    route.fulfill({ json: { items: [{ id: 88, name: 'Studio camera', sku: 'SC1', category: 'Video > Cameras', device_count: 3 }], total: 1 } }),
  );
  await page.route('**/api/v1/stockwire/products/88/device-specs', (route) =>
    route.fulfill({
      json: { id: 88, name: 'Studio camera', connector_groups: [{ connector: 'sdi', direction: 'out', count: 1, signal: 'video' }], power_inlet: 'iec_c13' },
    }),
  );
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^video$/i).click();

  const row = page.getByTestId('video-video_input-table').locator('tbody tr').filter({ has: page.locator('input') }).first();
  await row.getByTestId('video-source-picker').first().click();
  await page.keyboard.type('studio');
  await page.locator('.q-menu .q-item', { hasText: 'Studio camera' }).click();
  const lists = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/video-lists`, { headers })).json()) as {
      inputs: { source_label: string; stockwire_product_id: string | null }[];
    }[];
  await expect.poll(async () => (await lists())[0]?.inputs[0]?.stockwire_product_id).toBe('88');
  expect((await lists())[0].inputs[0].source_label).toBe('Studio camera');

  // the chain dialog searches Stockwire too: the product becomes a device with its connectors
  await row.getByTestId('edit-video-chain').click();
  await page.getByTestId('chain-add-step').click();
  await page.getByTestId('chain-stockwire').first().click();
  await page.keyboard.type('studio');
  await page.locator('.q-menu .q-item', { hasText: 'Studio camera' }).click();
  await page.getByTestId('chain-save').click();
  await expect
    .poll(async () => {
      const devices = (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json()) as any[];
      const cam = devices.find((d) => d.name === 'Studio camera');
      return cam && [cam.device_type, cam.ports.length];
    })
    .toEqual(['camera', 1]);
});

test('a plain device such as an LED wall can be hung on a rigging point', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Hang ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  await post(request, headers, `${g}/rigging-points`, { name: 'Truss A', weight_capacity_kg: 500 });
  await post(request, headers, `${g}/audio-devices`, { name: 'LED wall', device_type: 'screen', power_watts: 3500, weight_kg: 120 });
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/rigging & power|rigg & ström/i).click();
  await page.getByTestId('load-row').first().getByTestId('load-point').click();
  await page.locator('.q-menu .q-item', { hasText: 'Truss A' }).click();
  await expect(page.getByTestId('truss-load')).toContainText('120');
  await expect(page.getByTestId('load-rigging-status')).toContainText(/Rigging: OK|Rigg: OK/);
  await expect(page.getByTestId('load-power-status')).toContainText(/Power: Unpowered|Ström: Utan ström/);
  const graph = (await (await request.get(`${API_BASE}/api/v1${g}`, { headers })).json()) as any;
  const wall = graph.devices.find((d: any) => d.name === 'LED wall');
  expect(wall.attributes.rigging_point_id).toBeTruthy();
});

test('an outlet is added straight from the map, creating the venue for the job when it has none', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (
    await post(request, headers, '/jobs', { title: `E2E Map outlet ${Date.now()}`, stage_width_cm: 1000, stage_height_cm: 600 })
  ).id as string;
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('add-outlet-map').click();
  await page.getByRole('button', { name: /^ok$/i }).click();
  await expect(page.getByTestId('outlet-inspector')).toBeVisible();
  const job = async () => (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}`, { headers })).json()) as any;
  await expect.poll(async () => (await job()).venue_id).toBeTruthy();
  expect((await job()).stage_width_cm).toBe(1000);
  const outlets = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/power-outlets`, { headers })).json()) as any[];
  await expect.poll(async () => (await outlets()).length).toBe(1);

  // the venue now exists, so a second outlet needs no question
  await page.getByTestId('add-outlet-map').click();
  await expect.poll(async () => (await outlets()).length).toBe(2);
});

test('a speaker is added from the gear menu with its coverage and linked to an output point', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Speaker ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const list = await post(request, headers, `${g}/lists`, { name: 'FOH' });
  const out = await post(request, headers, `${g}/lists/${list.id}/outputs`, { name: 'Main L' });
  const amp = await post(request, headers, `${g}/audio-devices`, { name: 'Amp', device_type: 'other' });
  const chain = await request.put(`${API_BASE}/api/v1${g}/outputs/${out.id}/chain`, { headers, data: { steps: [{ device_id: amp.id }] } });
  expect(chain.status()).toBe(200);
  await page.goto(`/jobs/${jobId}/workspace`);

  await page.getByTestId('add-gear-element').click();
  await page.getByTestId('add-gear-speaker_main').click();
  const elements = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, { headers })).json()) as any[];
  await expect.poll(async () => (await elements())[0]?.element_type).toBe('speaker_main');
  expect([(await elements())[0].coverage_angle_h, (await elements())[0].coverage_distance_m]).toEqual([90, 30]);
  await expect(page.getByTestId('speaker-section')).toBeVisible();

  await page.getByTestId('coverage-distance').fill('45');
  await page.getByTestId('coverage-distance').press('Enter');
  await expect.poll(async () => (await elements())[0]?.coverage_distance_m).toBe(45);
  await page.getByTestId('element-output-point').click();
  await page.locator('.q-menu .q-item', { hasText: 'Main L' }).click();
  await expect.poll(async () => (await elements())[0]?.linked_output_point_id).toBeTruthy();

  // a camera takes (or makes) a camera device
  await page.getByTestId('add-gear-element').click();
  await page.getByTestId('add-gear-camera').click();
  await expect.poll(async () => (await elements()).find((e) => e.element_type === 'camera')?.linked_device_id).toBeTruthy();
  await expect(page.getByTestId('camera-section')).toBeVisible();
});

test('the audience area is outlined on the map, saved on the job, cleared and kept on the venue', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Audience ${Date.now()}` })).id as string;
  await page.goto(`/jobs/${jobId}/workspace`);
  const job = async () => (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}`, { headers })).json()) as any;
  const canvas = page.getByTestId('workspace-canvas');
  await expect(canvas).toBeVisible();

  await page.getByTestId('audience-menu').click();
  await page.getByTestId('audience-draw').click();
  await expect(page.getByTestId('audience-bar')).toBeVisible();
  await expect(page.getByTestId('audience-finish')).toBeDisabled();
  const box = (await canvas.boundingBox())!;
  for (const [x, y] of [[60, 200], [260, 200], [260, 300]]) {
    await canvas.click({ position: { x: Math.min(x, box.width - 5), y: Math.min(y, box.height - 5) } });
  }
  await expect(page.getByTestId('audience-finish')).toBeEnabled();
  await page.getByTestId('audience-finish').click();
  await expect.poll(async () => (await job()).audience_polygon.length).toBe(3);

  await page.getByTestId('audience-menu').click();
  await page.getByTestId('audience-clear').click();
  await expect.poll(async () => (await job()).audience_polygon.length).toBe(0);
});

test('a channel is paired as stereo with its neighbour and a wireless channel keeps pack and frequency', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Stereo ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const list = await post(request, headers, `${g}/lists`, { name: 'FOH' });
  await post(request, headers, `${g}/lists/${list.id}/channels`, { channel_number: 1, source_label: 'Piano', input_type: 'wireless' });
  const channels = async () =>
    (((await (await request.get(`${API_BASE}/api/v1${g}`, { headers })).json()) as any).devices as any[])
      .filter((d) => d.kind === 'channel')
      .sort((a, b) => a.attributes.channel_number - b.attributes.channel_number);
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();

  await page.getByTestId('wireless-pack').fill('Shure P10T');
  await page.getByTestId('wireless-pack').press('Enter');
  // the second edit waits for the first save: both patch the same row, so it needs the new revision
  await expect.poll(async () => (await channels())[0].attributes.wireless_pack).toBe('Shure P10T');
  await page.getByTestId('wireless-frequency-mhz').fill('606.250');
  await page.getByTestId('wireless-frequency-mhz').press('Enter');
  await expect.poll(async () => (await channels())[0].attributes.wireless_pack).toBe('Shure P10T');
  await expect.poll(async () => (await channels())[0].attributes.wireless_frequency_mhz).toBe(606.25);

  // ticking stereo makes the missing partner channel 2 and labels the legs L and R
  await page.getByTestId('channel-stereo').first().click();
  await expect.poll(async () => (await channels()).length).toBe(2);
  await expect.poll(async () => (await channels()).map((c) => c.name)).toEqual(['Piano L', 'Piano R']);
  const both = await channels();
  expect(both.map((c) => c.attributes.stereo_channel)).toEqual([2, 1]);
  expect(both[1].attributes.input_type).toBe('wireless');
  await expect(page.getByTestId('stereo-side')).toHaveText([/L/, /R/]);

  await page.getByTestId('channel-stereo').first().click();
  await expect.poll(async () => (await channels()).every((c) => !c.attributes.stereo)).toBe(true);
});

test('a channel list gets a mixer size that fills it with the empty inputs and outputs it is missing', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  // Enable the integration so the mixer (set-mixer) control is present.
  await enableStockwire(request);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Mixer ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const list = await post(request, headers, `${g}/lists`, { name: 'FOH' });
  await post(request, headers, `${g}/lists/${list.id}/channels`, { channel_number: 1, source_label: 'Kick' });
  const devices = async () =>
    (((await (await request.get(`${API_BASE}/api/v1${g}`, { headers })).json()) as any).devices as any[]);
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();

  await expect(page.getByTestId('list-mixer')).toBeVisible();
  await page.getByTestId('set-mixer').click();
  await page.getByTestId('mixer-inputs').fill('4');
  await page.getByTestId('mixer-buses').fill('2');
  await page.getByTestId('mixer-save').click();

  await expect.poll(async () => (await devices()).filter((d) => d.kind === 'channel').length).toBe(4);
  await expect.poll(async () => (await devices()).filter((d) => d.kind === 'output').length).toBe(2);
  const saved = (await devices()).find((d) => d.id === list.id);
  expect([saved.attributes.mixer_inputs, saved.attributes.mixer_buses]).toEqual([4, 2]);
  // the legacy list the Stockwire sync reads carries the same size
  const legacy = (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, { headers })).json()) as any[];
  expect(legacy[0].mixer_inputs).toBe(4);
  await expect(page.getByTestId('list-mixer')).toContainText('4');
});

test('a camera takes its sensor width from a standard size or from the diagonal and aspect ratio', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Sensor ${Date.now()}` })).id as string;
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(devices|enheter)$/i).click();

  await page.getByTestId('new-device').click();
  await page.getByTestId('device-name').fill('Cam A');
  await page.getByTestId('device-type').click();
  await page.locator('.q-menu .q-item', { hasText: /^Camera$/ }).click();
  await expect(page.getByTestId('sensor-calculator')).toBeVisible();

  // a standard size fills the width, the aspect ratio and the diagonal
  await page.getByTestId('sensor-preset').click();
  await page.locator('.q-menu .q-item', { hasText: 'Super 35' }).click();
  await expect(page.getByLabel(/sensor width/i)).toHaveValue('24.9');
  await expect(page.getByTestId('sensor-aspect')).toHaveValue('4:3');

  // or the width is worked out from the spec sheet: 11 mm at 16:9 is about 9.59 mm wide
  await page.getByTestId('sensor-aspect').fill('16:9');
  await page.getByTestId('sensor-diagonal').fill('11');
  await expect(page.getByTestId('sensor-calc-text')).toContainText('9.59');
  await page.getByTestId('sensor-use-calculated').click();
  await expect(page.getByLabel(/sensor width/i)).toHaveValue('9.59');
  await page.getByTestId('device-save').click();

  const legacy = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })).json())[0];
  await expect.poll(async () => (await legacy())?.sensor_width_mm).toBeCloseTo(9.59, 2);
});

test('bulk-added channels can be patched into a device straight away', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Bulk ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  await post(request, headers, `${g}/lists`, { name: 'FOH' });
  await post(request, headers, `${g}/audio-devices`, { name: 'Stagebox A', device_type: 'analog_stagebox' });
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();

  await page.getByTestId('bulk-channels').click();
  await page.getByTestId('list-bulk-device').click();
  await page.locator('.q-menu .q-item', { hasText: 'Stagebox A' }).click();
  await page.getByTestId('list-bulk-create').click();

  const graph = async () => (await (await request.get(`${API_BASE}/api/v1${g}`, { headers })).json()) as any;
  await expect.poll(async () => (await graph()).devices.filter((d: any) => d.kind === 'channel').length).toBe(8);
  // every new channel has one chain edge into the stagebox
  await expect
    .poll(async () => {
      const data = await graph();
      const box = data.devices.find((d: any) => d.name === 'Stagebox A');
      const channelIds = new Set(data.devices.filter((d: any) => d.kind === 'channel').map((d: any) => d.id));
      return data.edges.filter((e: any) => channelIds.has(e.attributes?.chain) && (e.dst_device_id === box.id || e.src_device_id === box.id)).length;
    })
    .toBe(8);
});

test('the inspector shows how much of a device\'s ports are in use', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Ports ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const list = await post(request, headers, `${g}/lists`, { name: 'FOH' });
  const channel = await post(request, headers, `${g}/lists/${list.id}/channels`, { source_label: 'Kick' });
  const box = await post(request, headers, `${g}/audio-devices`, { name: 'Stagebox P', device_type: 'analog_stagebox' });
  const chain = await request.put(`${API_BASE}/api/v1${g}/channels/${channel.id}/chain`, {
    headers,
    data: { steps: [{ device_id: box.id, connector: 'xlr3' }] },
  });
  expect(chain.status()).toBe(200);
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();
  await dataRows(page).first().locator('td').nth(1).click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Stagebox P');
  await expect(page.getByTestId('port-usage')).toBeVisible();
  await expect(page.getByTestId('port-usage-row').first()).toContainText(/\d+\/\d+/);

  // the same usage is in the device dialog of the Devices tab, and a Stockwire category as a kind
  // (no translation) is shown as it is
  await page.getByTestId('mode-toggle').getByText(/^(devices|enheter)$/i).click();
  await page.getByTestId('edit-device').first().click();
  await expect(page.locator('.q-dialog').getByTestId('port-usage')).toBeVisible();
});

test('the device dialog says which weight and power value is in use', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Hints ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/graph/audio-devices`, { name: 'Amp H', device_type: 'other', weight_kg: 12 });
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(devices|enheter)$/i).click();
  await page.getByTestId('edit-device').first().click();
  // typed in here for the weight, nothing set for the power
  await expect(page.locator('.q-field', { has: page.getByTestId('device-weight') })).toContainText(/value entered here is in use|värde som anges här/i);
  await expect(page.locator('.q-field', { has: page.getByTestId('device-power') })).toContainText(/not set|inte satt|ej satt/i);
});

test('the gear behind a channel or a video input is edited from its list', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  // Enable the integration so the mixer (list-mixer-devices) control is present.
  await enableStockwire(request);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E ListEdit ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const list = await post(request, headers, `${g}/lists`, { name: 'FOH' });
  const channel = await post(request, headers, `${g}/lists/${list.id}/channels`, { source_label: 'Kick' });
  const desk = await post(request, headers, `${g}/audio-devices`, { name: 'Desk', device_type: 'mixer' });
  const put = await request.put(`${API_BASE}/api/v1${g}/channels/${channel.id}/chain`, {
    headers,
    data: { steps: [{ device_id: desk.id }] },
  });
  expect(put.status()).toBe(200);
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();

  // the console is on the list's mixer card; it opens in the inspector, details in its dialog
  await expect(page.getByTestId('list-mixer-devices')).toContainText('Desk');
  await page.getByTestId('list-mixer-devices').getByTestId('chain-device').first().click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Desk');
  await page.getByTestId('inspector-edit-details').click();
  await expect(page.getByTestId('device-name')).toHaveValue('Desk');
  await page.getByTestId('device-name').fill('Console FOH');
  await page.getByTestId('device-save').click();
  const named = async () =>
    (((await (await request.get(`${API_BASE}/api/v1${g}`, { headers })).json()) as any).devices as any[]).find(
      (d) => d.id === desk.id,
    ).name;
  await expect.poll(named).toBe('Console FOH');
  await expect(page.getByTestId('list-mixer-devices')).toContainText('Console FOH');
});

test('a channel source is a device that opens in the inspector', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Source ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const list = await post(request, headers, `${g}/lists`, { name: 'FOH' });
  const channel = await post(request, headers, `${g}/lists/${list.id}/channels`, { source_label: 'Vox' });
  await post(request, headers, `${g}/audio-devices`, { name: 'SM58 Vox', device_type: 'other' });
  const channelNode = async () =>
    (((await (await request.get(`${API_BASE}/api/v1${g}`, { headers })).json()) as any).devices as any[]).find(
      (d) => d.id === channel.id,
    );
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();

  // picking a device of the job links it to the channel
  await expect(page.getByTestId('open-source-device')).toHaveCount(0);
  await page.getByTestId('source-picker').click();
  await page.keyboard.type('SM58');
  await page.locator('.q-menu .q-item', { hasText: 'SM58 Vox' }).click();
  await expect.poll(async () => (await channelNode()).attributes.source_device_id).toBeTruthy();
  expect((await channelNode()).attributes.device).toBe('SM58 Vox');

  // and one click opens that device in the inspector, with its details dialog a click away
  await page.getByTestId('open-source-device').click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('SM58 Vox');
  await page.getByTestId('inspector-edit-details').click();
  await expect(page.getByTestId('device-name')).toHaveValue('SM58 Vox');
});

test('each device box in the show flow and each step in the edit flow has an edit button', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E FlowEdit ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const list = await post(request, headers, `${g}/lists`, { name: 'FOH' });
  const channel = await post(request, headers, `${g}/lists/${list.id}/channels`, { source_label: 'Kick' });
  const box = await post(request, headers, `${g}/audio-devices`, { name: 'Stagebox F', device_type: 'analog_stagebox' });
  const put = await request.put(`${API_BASE}/api/v1${g}/channels/${channel.id}/chain`, {
    headers,
    data: { steps: [{ device_id: box.id }] },
  });
  expect(put.status()).toBe(200);
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();

  // show flow: the box opens the device in the inspector and the flow closes
  await page.getByRole('button', { name: /show signal flow|visa signalväg|flow/i }).first().click();
  await page.getByTestId('flow-edit-device').first().click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Stagebox F');

  // edit flow: a step opens the device dialog on top of the chain dialog
  await page.getByTestId('edit-chain').first().click();
  await page.getByTestId('chain-edit-device').first().click();
  await expect(page.getByTestId('device-name')).toHaveValue('Stagebox F');
});

test('replacing or clearing a source removes the device it created, but not one that is in use', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Orphan ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const list = await post(request, headers, `${g}/lists`, { name: 'FOH' });
  await post(request, headers, `${g}/lists/${list.id}/channels`, { source_label: 'Vox' });
  const second = await post(request, headers, `${g}/lists/${list.id}/channels`, { source_label: 'Gtr' });
  await post(request, headers, `${g}/audio-devices`, { name: 'Mic A', device_type: 'other' });
  await post(request, headers, `${g}/audio-devices`, { name: 'Mic B', device_type: 'other' });
  const names = async () =>
    (((await (await request.get(`${API_BASE}/api/v1${g}`, { headers })).json()) as any).devices as any[])
      .filter((d) => d.name.startsWith('Mic '))
      .map((d) => d.name)
      .sort();
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();

  const pick = async (row: number, name: string) => {
    await page.getByTestId('source-picker').nth(row).click();
    await page.keyboard.type(name);
    // not the "use as typed" row: the device already in the job
    await page.locator('.q-menu .q-item', { hasText: `${name} ·` }).click();
  };
  await pick(0, 'Mic A');
  await expect(page.getByTestId('open-source-device')).toHaveCount(1);
  // replacing Mic A with Mic B removes Mic A, which nothing else used
  await pick(0, 'Mic B');
  await expect.poll(names).toEqual(['Mic B']);
  // Mic B is also the second channel's source, so clearing the first keeps it
  await pick(1, 'Mic B');
  await page.getByRole('button', { name: 'Clear' }).first().click();
  await expect(page.getByTestId('open-source-device')).toHaveCount(1);
  expect(await names()).toEqual(['Mic B']);
  void second;
});

test('on a phone every channel is a card with its kind, source, stand, connector, wireless fields and notes', async ({ page, request }) => {
  await login(page);
  await page.setViewportSize({ width: 390, height: 800 });
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Phone ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  const list = await post(request, headers, `${g}/lists`, { name: 'FOH' });
  const channel = await post(request, headers, `${g}/lists/${list.id}/channels`, {
    channel_number: 1,
    source_label: 'Lead',
    input_type: 'wireless',
    connector: 'xlr3',
    phantom_power: true,
    stand_type: 'Boom',
  });
  const node = async () =>
    (((await (await request.get(`${API_BASE}/api/v1${g}`, { headers })).json()) as any).devices as any[]).find(
      (d) => d.id === channel.id,
    );
  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('mode-toggle').getByText(/^(sound|ljud)$/i).click();

  // the summary line says what is set without opening anything
  const card = page.getByTestId('channel-card').first();
  await expect(card).toContainText('Wireless');
  await expect(card).toContainText('48V');
  await expect(card).toContainText('Boom');

  // the same editors as the table are under Details
  await card.getByTestId('channel-card-details').click();
  await card.getByLabel(/bodypack|beltpack/i).fill('Shure P10T');
  await card.getByLabel(/bodypack|beltpack/i).press('Enter');
  await expect.poll(async () => (await node()).attributes.wireless_pack).toBe('Shure P10T');
  await card.getByLabel(/notes|anteckningar/i).last().fill('Hand over at soundcheck');
  await card.getByLabel(/notes|anteckningar/i).last().press('Tab');
  await expect.poll(async () => (await node()).notes).toBe('Hand over at soundcheck');
  const box = await page.getByTestId('channel-cards').boundingBox();
  expect(box && box.x >= 0 && box.x + box.width <= 390).toBe(true);
});

test('on a phone lights and video rows are cards with every editor, and power loads stack', async ({ page, request }) => {
  await login(page);
  await page.setViewportSize({ width: 390, height: 800 });
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Phone2 ${Date.now()}` })).id as string;
  const g = `/jobs/${jobId}/graph`;
  await post(request, headers, `${g}/fixtures`, { purpose: 'Wash 1', footprint: 8, fixture_type: 'MAC Aura' });
  const vlist = await post(request, headers, `${g}/video-lists`, { name: 'Cameras' });
  await post(request, headers, `${g}/video-lists/${vlist.id}/inputs`, { source_label: 'Cam 1', connector: 'sdi' });
  await post(request, headers, `${g}/rigging-points`, { name: 'Truss A', weight_capacity_kg: 500 });
  await post(request, headers, `${g}/power-nodes`, {
    name: 'Mains',
    kind: 'source',
    feed_connector: 'cee63_3p',
    rating_amps: 63,
    outputs: [{ connector: 'cee32_3p', count: 1 }],
  });
  const graphNow = async () => (await (await request.get(`${API_BASE}/api/v1${g}`, { headers })).json()) as any;
  const noSideScroll = async (testId: string) => {
    const box = await page.getByTestId(testId).first().boundingBox();
    expect(box && box.x >= 0 && box.x + box.width <= 390).toBe(true);
  };
  await page.goto(`/jobs/${jobId}/workspace`);

  // lights: the card has the fixture's state and the editors under Details
  await page.getByTestId('mode-toggle').getByText(/^(lights|ljus)$/i).click();
  const fixture = page.getByTestId('fixture-card').first();
  await expect(fixture).toContainText('MAC Aura');
  await expect(fixture).toContainText('8 ch');
  await fixture.getByText(/^details$|^detaljer$/i).click();
  await fixture.getByLabel(/location|placering/i).fill('Truss 2');
  await fixture.getByLabel(/location|placering/i).press('Tab');
  await expect
    .poll(async () => (await graphNow()).devices.find((d: any) => d.kind === 'fixture')?.attributes.location)
    .toBe('Truss 2');
  await noSideScroll('fixture-cards');

  // video: the card says what the input is and has source, type, connector and notes under Details
  await page.getByTestId('mode-toggle').getByText(/^(video)$/i).click();
  const input = page.getByTestId('video-card').first();
  await expect(input.locator('input').first()).toHaveValue('Cam 1');
  await expect(input).toContainText(/sdi/i);
  await input.getByText(/^details$|^detaljer$/i).click();
  await input.getByLabel(/notes|anteckningar/i).fill('Wide shot');
  await input.getByLabel(/notes|anteckningar/i).press('Tab');
  await expect
    .poll(async () => (await graphNow()).devices.find((d: any) => d.kind === 'video_input')?.notes)
    .toBe('Wide shot');
  await noSideScroll('video-video_input-cards');

  // power: a load is stacked, so its three pickers are as wide as the phone, not squeezed
  await page.getByTestId('mode-toggle').getByText(/rigging & power|rigg & ström/i).click();
  const row = page.getByTestId('load-row').first();
  await expect(row).toBeVisible();
  for (const id of ['load-point', 'load-node', 'load-connector']) {
    const box = await row.getByTestId(id).locator('xpath=ancestor::*[contains(@class,"q-field")][1]').boundingBox();
    expect(box && box.width > 250 && box.x >= 0 && box.x + box.width <= 390).toBe(true);
  }
});

test('when the stockwire integration is disabled, every stockwire control is hidden but the settings tab stays', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  // Disable before the UI logs in so loadIntegration() picks up the disabled flag on first load.
  await setStockwireEnabled(request, false);
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Disabled ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Lead mic',
    stockwire_product_id: '4242',
    stockwire_product_name: 'SM58',
    stockwire_booked: false,
  });
  await page.goto(`/jobs/${jobId}/workspace`);

  // Job header buttons are gone entirely (v-if removes them from the DOM, so count is 0).
  await expect(page.getByTestId('open-catalog')).toHaveCount(0);
  await expect(page.getByTestId('open-availability')).toHaveCount(0);
  await expect(page.getByTestId('open-in-stockwire')).toHaveCount(0);

  // Table mode: the stockwire column (booking status / linked product) is dropped and the
  // "request to add" action is hidden.
  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();
  await expect(page.getByTestId('workspace-table')).toBeVisible();
  await expect(page.locator('th', { hasText: /stockwire/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /request to add to stockwire job booking/i })).toHaveCount(0);

  // Device creation: the "from Stockwire" picker is removed.
  await page.getByTestId('mode-toggle').getByText(/^devices$|^enheter$/i).click();
  await page.getByTestId('new-device').click();
  await expect(page.getByTestId('device-from-stockwire')).toHaveCount(0);

  // The Settings stockwire tab must remain reachable so the integration can be re-enabled.
  await page.goto('/settings');
  await expect(page.getByTestId('settings-tab-stockwire')).toBeVisible();
});

