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

test('the workspace opens as a canvas, places unplaced devices and keeps data when switching to the list', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  const { jobId, headers, mic } = await seedGraph(page, request);
  await page.goto(`/jobs/${jobId}/workspace`);

  await expect(page.getByTestId('workspace-canvas')).toBeVisible();
  await expect.poll(async () => {
    const graph = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })).json();
    return graph.devices.every((d: { canvas_x_cm: number | null }) => d.canvas_x_cm !== null);
  }).toBe(true);

  await page.getByTestId('mode-toggle').getByText(/channel list|kanallista/i).click();
  await expect(page.getByTestId('workspace-table')).toBeVisible();
  await expect(dataRows(page)).toHaveCount(2);
  await expect(page.getByRole('button', { name: /request to add to stockwire job booking/i })).toBeVisible();

  const graph = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })).json();
  const kept = graph.devices.find((d: { id: string }) => d.id === mic.id);
  expect(kept.stockwire_product_id).toBe('4242');
  expect(kept.canvas_x_cm).not.toBeNull();
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

  await page.getByTestId('mode-toggle').getByText(/channel list|kanallista/i).click();
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
  await page.getByTestId('mode-toggle').getByText(/channel list|kanallista/i).click();

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
  // zoom is 0.8; each device box is 96x40 px with its top-left at (cm * 0.8)
  const from = { x: box.x + 100 * 0.8 + 48, y: box.y + 100 * 0.8 + 20 };
  const to = { x: box.x + 500 * 0.8 + 48, y: box.y + 100 * 0.8 + 20 };
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
  // drop point (400, 300) px at zoom 0.8, snapped to the 10 cm grid
  expect(Math.abs(dropped.canvas_x_cm - 500)).toBeLessThanOrEqual(10);
  expect(Math.abs(dropped.canvas_y_cm - 375)).toBeLessThanOrEqual(10);

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
  await page.getByTestId('mode-toggle').getByText(/channel list|kanallista/i).click();
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
