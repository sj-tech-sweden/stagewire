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
  const job = await post('/jobs', { title: `Inspector ${Date.now()}` });
  await post(`/jobs/${job.id}/graph/audio-devices`, { name: 'Lead mic', device_type: 'other' });
  return job.id as string;
}

async function selectFirstDevice(page: Page) {
  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();
  // rows with an input are the data rows (the table also renders spacer rows)
  await page
    .getByTestId('workspace-table')
    .locator('tbody tr')
    .filter({ has: page.locator('input') })
    .first()
    .locator('td')
    .nth(1)
    .click();
}

test('the inspector only takes room while something is selected, and closes to give it back', async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 1500, height: 900 });
  const jobId = await seed(page, request);
  await page.goto(`/jobs/${jobId}/workspace`);
  const dropZone = page.getByTestId('drop-zone');
  await expect(dropZone).toBeVisible();

  // nothing selected: no inspector column, the work area uses the full width
  await expect(page.getByTestId('inspector-panel')).toHaveCount(0);
  const full = (await dropZone.boundingBox())!.width;

  // selecting a device opens it and the work area gives up that width
  await selectFirstDevice(page);
  await expect(page.getByTestId('inspector-panel')).toBeVisible();
  await expect(page.getByTestId('inspector-name')).toHaveValue('Lead mic');
  await expect.poll(async () => (await dropZone.boundingBox())!.width).toBeLessThan(full - 150);

  // the close button hands the width back
  await page.getByTestId('inspector-close').click();
  await expect(page.getByTestId('inspector-panel')).toHaveCount(0);
  await expect.poll(async () => (await dropZone.boundingBox())!.width).toBeGreaterThan(full - 10);

  // Esc does the same, but not while typing in a field
  await selectFirstDevice(page);
  await expect(page.getByTestId('inspector-panel')).toBeVisible();
  await page.getByTestId('inspector-name').click();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('inspector-panel')).toBeVisible();
  await page.getByTestId('inspector-name').blur();
  await page.locator('body').click({ position: { x: 5, y: 5 } });
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('inspector-panel')).toHaveCount(0);
});
