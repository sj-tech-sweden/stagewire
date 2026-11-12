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
