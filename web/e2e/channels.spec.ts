import { test, expect } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

test('create a job and manage channel lists', async ({ page, request }) => {
  await login(page);

  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  const title = `E2E Show ${Date.now()}`;
  const created = await request.post(`${API_BASE}/api/v1/jobs`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { title, venue_name: 'E2E Hall' },
  });
  const jobId = (await created.json()).id;

  // Open the job detail page
  await page.goto(`/jobs/${jobId}`);
  await expect(page).toHaveURL(/\/jobs\//);
  await expect(page.locator('.text-h5')).toContainText(title);

  // Add a channel list via the dialog
  await page.getByRole('button', { name: /add list/i }).click();
  const listDialog = page.locator('.q-dialog');
  await listDialog.locator('input').first().fill('FOH');
  await listDialog.getByRole('button', { name: /save/i }).click();
  await expect(page.locator('.q-item', { hasText: 'FOH' }).first()).toBeVisible();

  // Add a channel to the list
  await page.getByRole('button', { name: /add channel/i }).click();
  const channelDialog = page.locator('.q-dialog');
  await channelDialog.locator('input').nth(0).fill('1');
  await channelDialog.locator('input').nth(1).fill('Kick In');
  await channelDialog.getByRole('button', { name: /save/i }).click();

  // Save is async; wait for the dialog to close, then the row appears.
  await expect(page.locator('.q-dialog')).toHaveCount(0);
  await expect(page.locator('table').first().getByRole('textbox')).toHaveValue('Kick In');
});
