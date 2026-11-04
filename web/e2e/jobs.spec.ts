import { test, expect } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

test('create a production job from the UI', async ({ page }) => {
  await login(page);

  const title = `E2E Show ${Date.now()}`;
  const venue = `E2E Hall ${Date.now()}`;
  await page.getByRole('button', { name: /new job/i }).click();

  const dialog = page.locator('.q-dialog');
  await dialog.locator('input').nth(0).fill(title);

  // The venue is a searchable picker; typing a name that does not match offers a "create" action.
  await dialog.locator('.q-select input').fill(venue);
  await dialog.getByRole('button', { name: /create new venue/i }).click();
  await expect(dialog.getByText(venue)).toBeVisible();

  await dialog.getByRole('button', { name: /create/i }).click();

  await expect(page.getByText(title)).toBeVisible();
  await expect(page.getByText(venue)).toBeVisible();
});

test('jobs can be searched and are listed newest first, a page at a time', async ({ page, request }) => {
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  const headers = { Authorization: `Bearer ${token}` };
  const tag = `findme-${Date.now()}`;
  for (const n of [1, 2]) {
    await request.post(`${API_BASE}/api/v1/jobs`, { headers, data: { title: `${tag} job ${n}` } });
  }
  await page.goto('/');
  // the newest job is at the top without any scrolling through older ones
  await expect(page.getByText(`${tag} job 2`)).toBeVisible();
  await page.getByTestId('job-search').fill(tag);
  await expect(page.getByText(`${tag} job 1`)).toBeVisible();
  await expect(page.getByTestId('jobs-footer')).toContainText('2');
  await page.getByTestId('job-search').fill('no-such-job-anywhere');
  await expect(page.getByText(`${tag} job 1`)).toHaveCount(0);
});
