import { test, expect } from '@playwright/test';
import { ensureAdmin, login } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

test('create a production job from the UI', async ({ page }) => {
  await login(page);

  const title = `E2E Show ${Date.now()}`;
  await page.getByRole('button', { name: /new job/i }).click();

  const dialog = page.locator('.q-dialog');
  await dialog.locator('input').nth(0).fill(title);
  await dialog.locator('input').nth(1).fill('E2E Hall');
  await dialog.getByRole('button', { name: /create/i }).click();

  await expect(page.getByText(title)).toBeVisible();
});
