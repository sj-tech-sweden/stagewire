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
  await expect(page.getByText('API base URL')).toBeVisible();
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

  // Open the job and its details dialog from the job card.
  await page.goto('/');
  await page.getByText(/NetBox Job \d+/).first().click();
  // The job page exposes a "Job details" action; open it via the details dialog.
  await page.getByRole('button', { name: /job details/i }).click();

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
  // NetBox IP block inside it) render.
  const device = (await (await request.post(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers: h, data: { name: 'NetBox Mixer', device_type: 'mixer' } })).json());

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

  // Open the device inspector via the workspace table row.
  await page.goto(`/jobs/${jobId}`);
  await page.getByTestId('workspace-table').getByText('NetBox Mixer').click();

  const networkPanel = page.getByTestId('network-panel');
  if (!(await page.getByTestId('network-netbox-prefix').isVisible())) {
    await networkPanel.click();
  }
  const prefixInput = page.getByTestId('network-netbox-prefix');
  await prefixInput.fill(cidr);
  await prefixInput.press('Tab'); // blur → fires @change → persists network_prefix
  await expect(prefixInput).toHaveValue(cidr);

  // Clicking Query must pass no argument (so it falls back to network_prefix),
  // never the PointerEvent that @click would otherwise hand it.
  await page.getByRole('button', { name: /query netbox ips/i }).click();
  await expect(queriedPrefix).toBe(cidr);

  // Pick the returned IP and assign it. The address sent to the backend must be
  // the plain string, not the {label,value} option object the select emits.
  await page.getByTestId('network-netbox-ip').click();
  await page.getByText('10.0.0.5/24').click();
  await page.getByRole('button', { name: /assign/i }).click();
  await expect(assignedBody as { address?: unknown }).toMatchObject({ address: '10.0.0.5/24' });
  expect(typeof (assignedBody as { address?: unknown }).address).toBe('string');

  await request.delete(`${API_BASE}/api/v1/jobs/${jobId}`, { headers: h });
});
