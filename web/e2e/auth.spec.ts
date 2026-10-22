import { test, expect } from '@playwright/test';
import { ensureAdmin, login } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

test('unauthenticated visit redirects to login', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/login/);
  await expect(page.getByText('Stagewire')).toBeVisible();
});

test('login with valid credentials reaches the jobs page', async ({ page }) => {
  await login(page);
  await expect(page.getByRole('main').getByText('Production jobs', { exact: true })).toBeVisible();
});

test('logout returns to the login page', async ({ page }) => {
  await login(page);
  await page.getByRole('button', { name: /admin@stagewire\.test/i }).click();
  await page.getByText(/log out/i).click();
  await expect(page).toHaveURL(/login/);
});
