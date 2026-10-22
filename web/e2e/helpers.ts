import { APIRequestContext } from '@playwright/test';

export const ADMIN = { email: 'admin@stagewire.test', password: 'Test1234!' };
export const API_BASE = 'http://localhost:8010';

export async function waitForApi(request: APIRequestContext, timeoutMs = 120_000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await request.get(`${API_BASE}/api/v1/health/live`);
      if (res.ok()) return;
    } catch {
      // API not reachable yet
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error('API did not become healthy in time');
}

export async function ensureAdmin(request: APIRequestContext): Promise<void> {
  await waitForApi(request);
  const status = await request.get(`${API_BASE}/api/v1/auth/bootstrap-status`);
  if (!status.ok()) return;
  const body = (await status.json()) as { setup_needed?: boolean };
  if (!body.setup_needed) return;
  await request.post(`${API_BASE}/api/v1/auth/setup`, {
    data: {
      email: ADMIN.email,
      password: ADMIN.password,
      first_name: 'Admin',
      last_name: 'Test',
    },
  });
}

export async function login(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/login');
  await page.locator('input[type="email"]').fill(ADMIN.email);
  await page.locator('input[type="password"]').fill(ADMIN.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  // Wait for an authenticated element rather than the URL: after sign-in the
  // SPA navigates client-side (history mode), so the address bar does not
  // reliably end in "/" and waiting on it flakes.
  await page.getByRole('button', { name: /admin@stagewire\.test/i }).waitFor();
}
