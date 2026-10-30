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
