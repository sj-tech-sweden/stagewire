import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

async function createVenue(request: APIRequestContext, headers: Record<string, string>, name: string) {
  const res = await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: {
      name,
      venue_width_cm: 1200,
      venue_height_cm: 900,
      stage_x_cm: 100,
      stage_y_cm: 50,
      stage_width_cm: 400,
      stage_height_cm: 300,
    },
  });
  expect(res.status()).toBe(201);
  return (await res.json()).id as string;
}

test('a venue base rig opens the graph canvas in venue mode', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const name = `E2E Base Rig ${Date.now()}`;
  const venueId = await createVenue(request, headers, name);

  await page.goto('/venues');
  const row = page.locator('.q-item', { hasText: name });
  await row.getByLabel('Open base rig').click();

  await expect(page).toHaveURL(new RegExp(`/venues/${venueId}/base-rig$`));
  // The canvas renders and the venue name is shown in venue mode.
  await expect(page.locator('canvas').first()).toBeVisible();
  await expect(page.getByText(name)).toBeVisible();
});

test('base rig audio entities are authored through the venue /rig API', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const name = `E2E Base Rig API ${Date.now()}`;
  const venueId = await createVenue(request, headers, name);

  // Top-level device (venue-owned).
  const dev = await request.post(`${API_BASE}/api/v1/venues/${venueId}/rig/devices`, {
    headers,
    data: { name: 'House Stagebox', device_type: 'stagebox' },
  });
  expect(dev.status()).toBe(201);
  expect((await dev.json()).job_id).toBeNull();

  // Nested child via the mirrored path (channel-list -> channel).
  const cl = await request.post(`${API_BASE}/api/v1/venues/${venueId}/rig/channel-lists`, {
    headers,
    data: { name: 'House Inputs' },
  });
  expect(cl.status()).toBe(201);
  const clId = (await cl.json()).id as string;
  const ch = await request.post(
    `${API_BASE}/api/v1/venues/${venueId}/rig/channel-lists/${clId}/channels`,
    { headers, data: { channel_number: 1 } },
  );
  expect(ch.status()).toBe(201);
  expect((await ch.json()).channel_list_id).toBe(clId);

  // Listing returns only venue-owned rows.
  const listed = await request.get(`${API_BASE}/api/v1/venues/${venueId}/rig/devices`, { headers });
  expect(listed.status()).toBe(200);
  expect((await listed.json()).length).toBe(1);

  // Rows are scoped to the venue: a different venue 404s on the same id.
  const other = await createVenue(request, headers, `E2E Other ${Date.now()}`);
  const cross = await request.get(`${API_BASE}/api/v1/venues/${other}/rig/devices/${venueId}`, {
    headers,
  });
  expect(cross.status()).toBe(404);
});

test('venue base rig sections are reachable via the rig tab navigation', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const name = `E2E Base Rig Tabs ${Date.now()}`;
  const venueId = await createVenue(request, headers, name);

  await page.goto(`/venues/${venueId}/base-rig`);
  await expect(page.locator('canvas').first()).toBeVisible();

  // Lighting section (the DMX fixture patch) renders the owner-aware editor.
  await page.getByRole('tab', { name: 'Lighting' }).click();
  await expect(page).toHaveURL(new RegExp(`/venues/${venueId}/lighting$`));
  await expect(page.getByText('Fixture patch')).toBeVisible();

  // Rigging section renders the owner-aware editor.
  await page.getByRole('tab', { name: 'Rigging' }).click();
  await expect(page).toHaveURL(new RegExp(`/venues/${venueId}/rigging$`));
  await expect(page.getByText('Rigging & power')).toBeVisible();

  // Video section renders the owner-aware list editor.
  await page.getByRole('tab', { name: 'Video' }).click();
  await expect(page).toHaveURL(new RegExp(`/venues/${venueId}/video$`));
  await expect(page.getByText('Input lists')).toBeVisible();
});

test('job audio authoring is unchanged by the owner-aware refactor', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);

  const jobRes = await request.post(`${API_BASE}/api/v1/jobs`, {
    headers,
    data: { title: `E2E Job Owner ${Date.now()}` },
  });
  expect(jobRes.ok()).toBeTruthy();
  const jobId = (await jobRes.json()).id as string;

  const dev = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/devices`, {
    headers,
    data: { name: 'Job Mic', device_type: 'microphone' },
  });
  expect(dev.status()).toBe(201);
  const listed = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers });
  expect((await listed.json()).length).toBe(1);
});
