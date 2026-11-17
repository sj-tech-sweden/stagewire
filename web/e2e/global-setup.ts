import { request as playwrightRequest } from '@playwright/test';
import { ADMIN, API_BASE, waitForApi } from './helpers';

// The app takes its UI language from the signed-in user's stored preference, and the test admin
// is shared by every spec. A long-lived database can keep it on Swedish (for example after a
// manual run), which breaks specs that match English labels. Pin it to English once per run; the
// history spec sets Swedish for its own check and restores English afterwards.
// The web server can be ready before the API, so wait for the API first. On a fresh database the
// admin does not exist yet and the default language is already English, so there is nothing to pin.
export default async function globalSetup(): Promise<void> {
  const request = await playwrightRequest.newContext();
  try {
    await waitForApi(request);
    const login = await request.post(`${API_BASE}/api/v1/auth/login`, { data: ADMIN });
    if (!login.ok()) return;
    const { access_token } = (await login.json()) as { access_token: string };
    const headers = { Authorization: `Bearer ${access_token}` };
    const me = (await (await request.get(`${API_BASE}/api/v1/auth/me`, { headers })).json()) as { id: string };
    await request.put(`${API_BASE}/api/v1/auth/users/${me.id}`, {
      headers,
      data: { preferred_language: 'en' },
    });
  } finally {
    await request.dispose();
  }
}
