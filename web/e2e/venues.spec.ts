import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

async function createJob(request: APIRequestContext, headers: Record<string, string>, body = {}) {
  const res = await request.post(`${API_BASE}/api/v1/jobs`, {
    headers,
    data: { title: `E2E Venue Show ${Date.now()}`, ...body },
  });
  expect(res.ok()).toBeTruthy();
  return (await res.json()).id as string;
}

test('a saved venue is assigned to a job and shown on the stage plot', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);

  const venueName = `E2E Hall ${Date.now()}`;
  const venueRes = await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: {
      name: venueName,
      venue_width_cm: 1200,
      venue_height_cm: 900,
      stage_x_cm: 100,
      stage_y_cm: 50,
      stage_width_cm: 400,
      stage_height_cm: 300,
    },
  });
  expect(venueRes.status()).toBe(201);
  const venueId = (await venueRes.json()).id as string;

  const jobId = await createJob(request, headers);
  const assign = await request.put(`${API_BASE}/api/v1/jobs/${jobId}/venue`, {
    headers,
    data: { venue_id: venueId },
  });
  expect(assign.ok()).toBeTruthy();
  expect((await assign.json()).venue_name).toBe(venueName);

  await page.goto(`/jobs/${jobId}/stage-plot`);
  await expect(page.getByLabel('Venue width (cm)')).toHaveValue('1200');
  await expect(page.getByLabel('Venue depth (cm)')).toHaveValue('900');
  await expect(page.getByLabel('Stage X (cm)')).toHaveValue('100');

  // With no elements yet the stage and venue still render on the canvas.
  await expect(page.locator('canvas').first()).toBeVisible();
});

test('speaker coverage can be shown on the stage plot', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);

  const jobId = await createJob(request, headers, {
    venue_width_cm: 1000,
    venue_height_cm: 1000,
    stage_x_cm: 0,
    stage_y_cm: 0,
    stage_width_cm: 500,
    stage_height_cm: 400,
  });
  const element = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, {
    headers,
    data: {
      element_type: 'speaker_main',
      position_x: 250,
      position_y: 300,
      width_cm: 42,
      height_cm: 72,
      rotation: 0,
      coverage_angle_h: 90,
      coverage_distance_m: 30,
    },
  });
  expect(element.status()).toBe(201);

  const coverage = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/coverage`, { headers });
  const body = await coverage.json();
  expect(body.speaker_count).toBe(1);
  expect(body.covered_pct).toBeGreaterThan(0);

  await page.goto(`/jobs/${jobId}/stage-plot`);
  await page.getByText('Sound coverage', { exact: true }).click();
  await expect(page.getByText(/Covered: \d+(\.\d+)?% of venue/)).toBeVisible();
});

test('sound and camera coverage have separate toggles', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = await createJob(request, headers, {
    venue_width_cm: 1000,
    venue_height_cm: 1000,
    stage_x_cm: 0,
    stage_y_cm: 0,
    stage_width_cm: 500,
    stage_height_cm: 400,
  });
  await page.goto(`/jobs/${jobId}/stage-plot`);
  const sound = page.getByRole('switch', { name: 'Sound coverage' });
  const camera = page.getByRole('switch', { name: 'Camera coverage' });
  await expect(sound).toBeVisible();
  await expect(camera).toBeVisible();
  await camera.click();
  await expect(camera).toHaveAttribute('aria-checked', 'true');
  await expect(sound).toHaveAttribute('aria-checked', 'false');
});

test('the venues page lists saved venues', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const name = `E2E Listed Venue ${Date.now()}`;
  await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: { name, venue_width_cm: 800, venue_height_cm: 600 },
  });

  await page.goto('/venues');
  await expect(page.getByText(name)).toBeVisible();
});

test('venue propagation status has strong contrast when editing a venue', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const name = `E2E Venue Status ${Date.now()}`;
  await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: { name, venue_width_cm: 800, venue_height_cm: 600 },
  });

  await page.goto('/venues');
  await page.getByText(name, { exact: true }).click();
  const status = page.getByRole('status');
  await expect(status).toBeVisible();
  await expect(status).toHaveClass(/text-blue-grey-10/);
  await expect(status).toHaveClass(/bg-blue-grey-2/);
});
