import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

async function post(
  request: APIRequestContext,
  headers: Record<string, string>,
  path: string,
  data: object,
) {
  const res = await request.post(`${API_BASE}/api/v1${path}`, { headers, data });
  expect(res.status(), `${path}: ${await res.text()}`).toBeLessThan(300);
  return res.json();
}

test('a crew member opens the read-only mobile view with a share token and no login', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share E2E ${Date.now()}` })).id;
  await post(request, headers, `/jobs/${jobId}/graph/devices`, {
    domain: 'audio',
    name: 'Stagebox A',
    kind: 'stagebox',
    attributes: { network_ip: '192.168.1.10', network_vlan: 120 },
  });

  // A logged-in user mints the share token; it is the only credential the crew view needs.
  const share = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/share`, { headers });
  expect(share.status()).toBe(200);
  const { token } = await share.json();
  expect(token).toBeTruthy();

  // The crew member lands straight on the view — no session, no login redirect.
  await page.goto(`/jobs/${jobId}/view?token=${token}`);
  const list = page.getByTestId('share-device-list');
  await expect(list).toBeVisible();
  await expect(page.getByText('Stagebox A')).toBeVisible();
  // The network metadata we seeded is surfaced read-only.
  await expect(page.getByText('192.168.1.10')).toBeVisible();

  // No editing affordances leak into the read-only view.
  await expect(page.getByTestId('inspector-name')).toHaveCount(0);
});

test('the mobile view rejects a missing or forged token', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share E2E ${Date.now()}` })).id;

  // No token at all.
  await page.goto(`/jobs/${jobId}/view`);
  await expect(page.getByTestId('share-error')).toBeVisible();

  // A tampered token.
  await page.goto(`/jobs/${jobId}/view?token=not-a-real-token`);
  await expect(page.getByTestId('share-error')).toBeVisible();
});

test('the workspace can generate a shareable QR + link for the crew view', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `Share E2E ${Date.now()}` })).id;

  await page.goto(`/jobs/${jobId}/workspace`);
  await page.getByTestId('open-share').click();
  await expect(page.getByTestId('share-qr')).toBeVisible();
  const link = await page.getByTestId('share-link').inputValue();
  expect(link).toContain(`/jobs/${jobId}/view?token=`);

  // Following the generated link opens the read-only view.
  await page.goto(link);
  await expect(page.getByTestId('share-device-list')).toBeVisible();
});
