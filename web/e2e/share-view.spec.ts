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
  // The network metadata we seeded is surfaced read-only.
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

  // Open the device in the inspector via the patch drawer.
  await page.getByTestId('patch-edit-from').first().click();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Stagebox A');
  await expect(page.getByTestId('stockwire-asset-panel')).toBeVisible();

  // Bind a Stockwire asset (the integration is off in e2e, so the code is stored locally).
  await page.getByTestId('bind-open').click();
  await expect(page.getByTestId('bind-code')).toBeVisible();
  await page.getByTestId('bind-code').fill('ASSET-XYZ');
  await page.getByTestId('bind-confirm').click();
  await expect(page.getByTestId('bind-result')).toBeVisible();

  // Close the dialog; the inspector now shows the bound asset and an unbind action.
  await page.getByRole('button', { name: 'Close' }).click();
  await expect(page.getByTestId('stockwire-asset-panel')).toContainText('ASSET-XYZ');
  await expect(page.getByTestId('bind-unbind')).toBeVisible();

  // The crew view reflects the binding read-only.
  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  const { token } = await share.json();
  await page.goto(`/jobs/${jobId}/view?token=${token}`);
  await expect(page.getByTestId('share-device-list')).toBeVisible();
  await expect(page.getByText('ASSET-XYZ')).toBeVisible();
});
