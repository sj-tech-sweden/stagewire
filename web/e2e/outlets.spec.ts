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

async function setupJobWithVenue(request: APIRequestContext, headers: Record<string, string>) {
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Outlets ${Date.now()}` })).id as string;
  const venue = await post(request, headers, '/venues', { name: `E2E Hall ${Date.now()}` });
  await request.put(`${API_BASE}/api/v1/jobs/${jobId}/venue`, { headers, data: { venue_id: venue.id } });
  return { jobId, venue };
}

test('an outlet can be added on the stage plot through the plot button', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId } = await setupJobWithVenue(request, headers);

  const loaded = page.waitForResponse((res) => res.url().includes('/power-outlets') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.waitForLoadState('networkidle');

  await page.getByRole('button', { name: 'Add outlet' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Name').fill('Stage L');
  await dialog.getByLabel('Connector').click();
  await page.getByRole('option', { name: 'Schuko 16 A', exact: true }).click();
  await dialog.getByRole('button', { name: 'Add outlet' }).click();

  await expect
    .poll(async () => {
      const outlets = await (
        await request.get(`${API_BASE}/api/v1/jobs/${jobId}/power-outlets`, { headers })
      ).json();
      return outlets.length;
    })
    .toBe(1);
});

test('a device can be wired to an outlet via connect power on the stage plot', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, venue } = await setupJobWithVenue(request, headers);

  const wash = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Wash', device_type: 'fixture' });
  await post(request, headers, `/jobs/${jobId}/plot-elements`, {
    element_type: 'moving_light',
    label: 'Wash',
    linked_device_id: wash.id,
    position_x: 300,
    position_y: 100,
  });
  // Outlet at the centre of the stage so its canvas position is predictable.
  await post(request, headers, `/venues/${venue.id}/power-outlets`, {
    name: 'Stage L',
    connector: 'schuko',
    x_cm: 600,
    y_cm: 350,
  });

  const loaded = page.waitForResponse((res) => res.url().includes('/power-nodes') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('Connect power', { exact: true })).toBeVisible();

  // Enter connect mode and click the outlet, then the device element.
  await page.getByRole('button', { name: 'Connect power' }).click();
  await expect(page.getByText('Pick a source')).toBeVisible();

  // The stage plot renders at a fixed 0.7 scale with no stage offset, so the
  // outlet (centre) and the Wash element map to these canvas pixels.
  const SCALE = 0.7;
  const canvas = page.locator('.konvajs-content canvas');
  const box = (await canvas.boundingBox())!;
  const outletPt = { x: 600 * SCALE, y: 350 * SCALE };
  const devicePt = { x: (300 + 20) * SCALE, y: (100 + 15) * SCALE };

  await page.mouse.click(box.x + outletPt.x, box.y + outletPt.y);
  await expect(page.getByText('Source selected').first()).toBeVisible();

  await page.mouse.click(box.x + devicePt.x, box.y + devicePt.y);

  await expect
    .poll(async () => {
      const nodes = await (
        await request.get(`${API_BASE}/api/v1/jobs/${jobId}/power-nodes`, { headers })
      ).json();
      return nodes.filter((n: { device_id: string | null }) => n.device_id === wash.id).length;
    })
    .toBe(1);
});

test('a rated-connector outlet can be wired to a device via connect power', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, venue } = await setupJobWithVenue(request, headers);

  const wash = await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Wash', device_type: 'fixture' });
  await post(request, headers, `/jobs/${jobId}/plot-elements`, {
    element_type: 'moving_light',
    label: 'Wash',
    linked_device_id: wash.id,
    position_x: 300,
    position_y: 100,
  });
  // A fixed-install connector needs a hand-entered rating; the source node must carry it.
  await post(request, headers, `/venues/${venue.id}/power-outlets`, {
    name: 'Stage L',
    connector: 'install_1p',
    rating_amps: 16,
    x_cm: 600,
    y_cm: 350,
  });

  const loaded = page.waitForResponse((res) => res.url().includes('/power-nodes') && res.ok());
  await page.goto(`/jobs/${jobId}/stage-plot`);
  await loaded;
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('Connect power', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Connect power' }).click();
  await expect(page.getByText('Pick a source')).toBeVisible();

  const SCALE = 0.7;
  const canvas = page.locator('.konvajs-content canvas');
  const box = (await canvas.boundingBox())!;
  const outletPt = { x: 600 * SCALE, y: 350 * SCALE };
  const devicePt = { x: (300 + 20) * SCALE, y: (100 + 15) * SCALE };

  await page.mouse.click(box.x + outletPt.x, box.y + outletPt.y);
  await expect(page.getByText('Source selected').first()).toBeVisible();

  await page.mouse.click(box.x + devicePt.x, box.y + devicePt.y);

  await expect
    .poll(async () => {
      const nodes = await (
        await request.get(`${API_BASE}/api/v1/jobs/${jobId}/power-nodes`, { headers })
      ).json();
      const deviceNodes = nodes.filter((n: { device_id: string | null }) => n.device_id === wash.id);
      const ratedSource = nodes.find(
        (n: { kind: string; rating_amps: number | null }) => n.kind === 'source' && n.rating_amps === 16,
      );
      return deviceNodes.length === 1 && !!ratedSource;
    })
    .toBe(true);
});
