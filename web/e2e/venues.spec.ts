import { test, expect, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

test('the venues page lists saved venues', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const name = `E2E Listed Venue ${Date.now()}`;
  await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: { name, venue_width_cm: 800, venue_height_cm: 600 },
  });

  await page.goto('/venues');
  await expect(page.getByText(name)).toBeVisible();
});

test('venue propagation status has strong contrast when editing a venue', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const name = `E2E Venue Status ${Date.now()}`;
  await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: { name, venue_width_cm: 800, venue_height_cm: 600 },
  });

  await page.goto('/venues');
  await page.getByText(name, { exact: true }).click();
  const status = page.getByRole('status');
  await expect(status).toBeVisible();
  await expect(status).toHaveClass(/text-blue-grey-10/);
  await expect(status).toHaveClass(/bg-blue-grey-2/);
});
