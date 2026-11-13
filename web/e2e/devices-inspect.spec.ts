import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function seed(page: Page, request: APIRequestContext) {
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  const headers = { Authorization: `Bearer ${token}` };
  const post = async (path: string, data: object) =>
    (await request.post(`${API_BASE}/api/v1${path}`, { headers, data })).json();
  const job = await post('/jobs', { title: `Devices inspect ${Date.now()}` });
  await post(`/jobs/${job.id}/graph/audio-devices`, { name: 'Lead mic', device_type: 'other' });
  return job.id as string;
}

// On a phone, the devices list only exposed edit/remove before; the inspector was unreachable.
// An explicit inspect button selects the device and opens the DeviceInspector (a bottom dialog
// on phones), driven by the shared graph.selectedDeviceId.
test('phone devices list: inspect button opens the DeviceInspector', async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 }); // lt.sm -> q-list, lt.md -> bottom dialog
  const jobId = await seed(page, request);
  await page.goto(`/jobs/${jobId}/workspace`);

  // Switch to the Devices mode (q-tabs, label localized as "Devices"/"Enheter").
  await page.getByTestId('mode-toggle').getByText(/^(devices|enheter)$/i).click();
  await expect(page.getByTestId('device-editor')).toBeVisible();

  // Tap the inspect action for the device row.
  await page.getByTestId('inspect-device').first().click();

  // The DeviceInspector opens (bottom dialog on phones) with the selected device's name.
  const inspectorName = page.getByTestId('inspector-name');
  await expect(inspectorName).toBeVisible();
  await expect(inspectorName).toHaveValue('Lead mic');

  // Closing the inspector clears the selection (the mobile dialog stays in the DOM but hides).
  await page.getByTestId('inspector-close').click();
  await expect(inspectorName).toBeHidden();
});
