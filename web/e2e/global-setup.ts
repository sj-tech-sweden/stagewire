import { ADMIN, API_BASE } from './helpers';

// The app takes its UI language from the signed-in user's stored preference, and the test admin
// is shared by every spec. A long-lived database can keep it on Swedish (for example after a
// manual run), which breaks specs that match English labels. Pin it to English once per run; the
// history spec sets Swedish for its own check and restores English afterwards.
export default async function globalSetup(): Promise<void> {
  const login = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: ADMIN.email, password: ADMIN.password }),
  });
  if (!login.ok) return;
  const { access_token } = (await login.json()) as { access_token: string };
  const headers = { Authorization: `Bearer ${access_token}`, 'Content-Type': 'application/json' };
  const me = (await (await fetch(`${API_BASE}/api/v1/auth/me`, { headers })).json()) as { id: string };
  await fetch(`${API_BASE}/api/v1/auth/users/${me.id}`, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ preferred_language: 'en' }),
  });
}
