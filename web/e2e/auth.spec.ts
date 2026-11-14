import { test, expect } from '@playwright/test';
import { ADMIN, API_BASE, ensureAdmin, login } from './helpers';

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

test('session persists across a page reload', async ({ page }) => {
  await login(page);
  // The access token is persisted in localStorage and the refresh token lives in
  // an httpOnly cookie; a reload must not force a fresh login.
  await page.reload();
  await expect(page.getByRole('main').getByText('Production jobs', { exact: true })).toBeVisible();
  const hasToken = await page.evaluate(() => !!localStorage.getItem('sw_access_token'));
  expect(hasToken).toBe(true);
});

test('httpOnly refresh cookie re-establishes the session when the access token is invalid', async ({
  page,
}) => {
  await login(page);
  // Simulate an expired/garbage access token in storage while the httpOnly refresh
  // cookie is still valid. The interceptor must refresh via the cookie and recover.
  await page.evaluate(() => localStorage.setItem('sw_access_token', 'garbage.invalid.token'));
  await page.reload();
  await expect(
    page.getByRole('main').getByText('Production jobs', { exact: true }),
    'silent refresh via the httpOnly cookie recovers the session',
  ).toBeVisible({ timeout: 15000 });
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  expect(token).not.toBe('garbage.invalid.token');
  expect(token).toBeTruthy();
});

test('SAML ACS fragment tokens establish a session and are cleared from the URL', async ({
  page,
  request,
}) => {
  await ensureAdmin(request);
  // Stand in for the SAML IdP ACS response: a real access token delivered in the URL
  // fragment (the backend's saml_acs 302s back with #access_token=...&refresh_token=...).
  const loginRes = await request.post(`${API_BASE}/api/v1/auth/login`, { data: ADMIN });
  const token = (await loginRes.json()).access_token as string;
  await page.goto(`/#access_token=${token}&refresh_token=ignored`);
  await expect(
    page.getByRole('main').getByText('Production jobs', { exact: true }),
    'the SAML fragment handler hydrates the user and lands on the jobs page',
  ).toBeVisible({ timeout: 15000 });
  await expect(page, 'the tokens are stripped from the URL bar').not.toHaveURL(/access_token=/);
  const stored = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  expect(stored).toBe(token);
});
