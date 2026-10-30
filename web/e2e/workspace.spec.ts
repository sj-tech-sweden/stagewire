import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

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

  await page.getByTestId('patch-tab-power').click();
  await expect(page.getByText(/no connections in this domain yet|inga kopplingar/i)).toBeVisible();

  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();
  await dataRows(page).first().locator('td').nth(1).click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Lead mic');
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
  await expect(page.getByText(/date-range availability|tillgänglighet per datum/i)).toBeVisible();
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

  await page.getByText(/add case contents|lägg till kåpans innehåll/i).click();
  await page.getByTestId('case-select').click();
  await page.getByRole('option', { name: /rack case/i }).click();
  await page.getByRole('button', { name: /add case and contents|lägg till kåpa/i }).click();
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

test('renaming a channel in the workspace list updates the channel list, and the canvas ignores channels', async ({
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
  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();
  const row = dataRows(page).first();
  await expect(row.locator('input').first()).toHaveValue('Kick');
  await row.locator('input').first().fill('Kick In');
  await row.locator('input').first().press('Enter');

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
  await page.getByTestId('mode-toggle').getByText(/channel lists|kanallistor/i).click();

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

  const universe = async () =>
    (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/dmx-universes`, { headers })).json())[0];
  await expect.poll(async () => (await universe())?.steps?.length).toBe(2);
  expect((await universe()).source_label).toBe('Lighting desk');
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
