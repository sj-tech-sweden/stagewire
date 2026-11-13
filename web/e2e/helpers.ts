import { APIRequestContext } from '@playwright/test';

export const ADMIN = { email: 'admin@stagewire.test', password: 'Test1234!' };
// Overridable so the suite can run against a stack on other ports (E2E_API_BASE / E2E_BASE_URL).
export const API_BASE = process.env.E2E_API_BASE || 'http://localhost:8010';

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

// Configure the stockwire-rental integration's `enabled` flag directly via the API.
// The frontend reads `settings.stockwire.enabled` on auth to decide which UI to show; CI seeds
// the integration disabled, so any test that exercises stockwire UI must enable it first. We log in
// via the API (independent of the page) to obtain a token, then PUT the setting. Doing this before
// the UI logs in means the app's `loadIntegration()` picks up the correct flag on its first load.
export async function setStockwireEnabled(request: APIRequestContext, enabled: boolean): Promise<void> {
  await waitForApi(request);
  const loginRes = await request.post(`${API_BASE}/api/v1/auth/login`, { data: ADMIN });
  const token = (await loginRes.json()).access_token as string;
  const res = await request.put(`${API_BASE}/api/v1/settings/stockwire`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      enabled,
      base_url: 'http://host.docker.internal:8000',
      public_url: 'http://host.docker.internal:8010',
    },
  });
  if (!res.ok()) throw new Error(`setStockwireEnabled failed: ${await res.text()}`);
}

export async function enableStockwire(request: APIRequestContext): Promise<void> {
  await setStockwireEnabled(request, true);
}

// Configure the NetBox integration's `enabled` flag directly via the API, mirroring
// setStockwireEnabled. The frontend reads `settings.netbox.enabled` on auth to decide
// which UI to show; CI seeds the integration disabled, so a test that exercises NetBox UI
// must enable it first (the app's loadIntegration() then picks up the flag on first load).
export async function setNetboxEnabled(request: APIRequestContext, enabled: boolean): Promise<void> {
  await waitForApi(request);
  const loginRes = await request.post(`${API_BASE}/api/v1/auth/login`, { data: ADMIN });
  const token = (await loginRes.json()).access_token as string;
  const res = await request.put(`${API_BASE}/api/v1/netbox`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      enabled,
      base_url: 'http://host.docker.internal:8000',
      public_url: 'http://host.docker.internal:8010',
      api_token: 'dev-token-placeholder',
    },
  });
  if (!res.ok()) throw new Error(`setNetboxEnabled failed: ${await res.text()}`);
}

export async function enableNetbox(request: APIRequestContext): Promise<void> {
  await setNetboxEnabled(request, true);
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
