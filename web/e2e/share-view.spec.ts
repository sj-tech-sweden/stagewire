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
