import { test, expect } from '@playwright/test';
import { ensureAdmin, login, enableNetbox, API_BASE } from './helpers';

// NetBox integration UI. The NetBox controls (Settings tab, per-job toggle, and
// the device inspector block) are gated behind the integration being enabled, so
// each test enables it via the API first — the same pattern as the stockwire specs.
test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

test('NetBox settings tab is present and reflects the enabled state', async ({ page, request }) => {
  await enableNetbox(request);
  await login(page);

  await page.goto('/settings');
  await page.getByTestId('settings-tab-netbox').click();

  // The NetBox base URL field and the enabled toggle are both visible.
  await expect(page.getByText(/NetBox/i).first()).toBeVisible();
  await expect(page.getByText('NetBox base URL')).toBeVisible();
  await expect(page.getByText('Enabled')).toBeVisible();
});

test('NetBox per-job toggle appears in the job details dialog when enabled', async ({
  page,
  request,
}) => {
  await enableNetbox(request);
  await login(page);

  // Open an existing job (create one via the API so we don't depend on UI job creation here).
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  const headers = { Authorization: `Bearer ${token}` };
  const createRes = await request.post(`${API_BASE}/api/v1/jobs`, {
    headers,
    data: { title: `NetBox Job ${Date.now()}` },
  });
  const jobId = (await createRes.json()).id as string;

  // Go straight to the job workspace — navigating from the home job card is racy against the
  // jobs accumulated by prior runs (the title regex would match stale cards). The workspace
  // header exposes a "Job details" action that opens the details dialog.
  await page.goto(`/jobs/${jobId}`);
  await page.getByTestId('open-job-details').click();

  await expect(page.getByTestId('job-netbox-enabled')).toBeVisible();
  await expect(page.getByTestId('job-sync-netbox')).toBeVisible();

  // Clean up the job we created.
  await request.delete(`${API_BASE}/api/v1/jobs/${jobId}`, { headers });
});

// Regression tests for the NetBox IP-assignment handlers. We stub the two backend
// routes (available-ips + assign-ip) at the browser level so the tests do not
// depend on a live NetBox: the assertions are about what the frontend *sends*,
// which is exactly where the two bugs lived.
test('querying NetBox IPs sends the CIDR, not the click event', async ({ page, request }) => {
  await enableNetbox(request);
  await login(page);
  const h = { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('sw_access_token'))}` };
  const jobId = (await (await request.post(`${API_BASE}/api/v1/jobs`, { headers: h, data: { title: `NetBox Query ${Date.now()}` } })).json()).id as string;
  // A mixer lives in the audio domain, which is what makes the Network & Control panel (and the
  // NetBox IP block inside it) render. The device must be a *graph* device: the workspace table
  // reads graph.devices, so creating it through the raw /devices AudioDevice endpoint would not
  // surface it in the workspace (and therefore not in the inspector).
  const batch = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/graph/devices/batch`, {
    headers: h,
    data: [{ domain: 'audio', kind: 'mixer', name: 'NetBox Mixer' }],
  });
  const deviceId = (await batch.json())[0].id as string;

  const cidr = '10.0.0.0/24';
  let queriedPrefix: string | null = null;
  await page.route('**/api/v1/netbox/available-ips**', (route) => {
    const url = new URL(route.request().url());
    queriedPrefix = url.searchParams.get('prefix');
    // Return one fake available address; the test only cares what was *sent*.
    return route.fulfill({ status: 200, json: [{ address: '10.0.0.5/24', family: 4 }] });
  });
  let assignedBody: unknown = null;
  await page.route('**/api/v1/netbox/assign-ip**', (route) => {
    assignedBody = route.request().postDataJSON();
    return route.fulfill({ status: 200, json: { ok: true, ip: '10.0.0.5/24', netbox_ip_id: 1, message: 'ok' } });
  });

  // Seed the device's NetBox prefix through the API and reload, so the graph store reflects it
  // before the inspector opens. Driving the prefix via the UI @change is racy against the async
  // PATCH round-trip; setting it directly keeps the test deterministic while still exercising the
  // real code path — queryNetboxIps() reads device.attributes.network_prefix at click time.
  await request.patch(`${API_BASE}/api/v1/jobs/${jobId}/graph/devices/${deviceId}`, {
    headers: h,
    data: { attributes: { network_prefix: cidr }, expected_revision: 1 },
  });

  // Open the device inspector: on the job workspace the device list (workspace-table) is rendered in
  // the "All gear" (list) mode, not the canvas, so switch to it first. The table renders the device
  // name in an editable input whose click is stopped (so it only focuses the field), so select the row
  // by clicking a non-name cell of the matching row — the same pattern the venue rig test uses.
  await page.goto(`/jobs/${jobId}`);
  await page.getByRole('tab', { name: 'All gear' }).click();
  const mixerRow = page
    .getByTestId('workspace-table')
    .locator('tr')
    .filter({ has: page.locator('input[value="NetBox Mixer"]') });
  await mixerRow.locator('td').nth(1).click();

  const networkPanel = page.getByTestId('network-panel');
  if (!(await page.getByTestId('network-netbox-prefix').isVisible())) {
    await networkPanel.click();
  }
  const prefixInput = page.getByTestId('network-netbox-prefix');
  await expect(prefixInput).toHaveValue(cidr);

  // Clicking Query must pass no argument (so it falls back to network_prefix),
  // never the PointerEvent that @click would otherwise hand it.
  await page.getByRole('button', { name: /query netbox ips/i }).click();
  // `queriedPrefix` is populated asynchronously by the stubbed route handler, so poll it
  // (expect(...).toBe would snapshot the still-null value at call time and fail).
  await expect.poll(() => queriedPrefix).toBe(cidr);

  // Pick the returned IP and assign it. The address sent to the backend must be
  // the plain string, not the {label,value} option object the select emits.
  await page.getByTestId('network-netbox-ip').click();
  await page.getByText('10.0.0.5/24').click();
  await page.getByRole('button', { name: /assign/i }).click();
  await expect.poll(() => assignedBody as { address?: unknown }).toMatchObject({ address: '10.0.0.5/24' });
  expect(typeof (assignedBody as { address?: unknown }).address).toBe('string');

  await request.delete(`${API_BASE}/api/v1/jobs/${jobId}`, { headers: h });
});
