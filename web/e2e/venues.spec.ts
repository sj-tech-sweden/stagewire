import { test, expect, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

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

test('venue geometry shapes persist and are exposed in the venues page', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const name = `E2E Geometry Venue ${Date.now()}`;
  const venueRes = await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: {
      name,
      venue_width_cm: 800,
      venue_height_cm: 600,
      footprint_shape: 'arena_circular',
      stage_shape: 'thrust',
    },
  });
  expect(venueRes.status()).toBe(201);
  const venue = await venueRes.json();
  expect(venue.footprint_shape).toBe('arena_circular');
  expect(venue.stage_shape).toBe('thrust');

  // The saved shapes are carried onto a job when the venue is assigned.
  const jobId = await createJob(request, headers);
  const assign = await request.put(`${API_BASE}/api/v1/jobs/${jobId}/venue`, {
    headers,
    data: { venue_id: venue.id },
  });
  expect(assign.ok()).toBeTruthy();
  const assigned = await assign.json();
  expect(assigned.venue_footprint_shape).toBe('arena_circular');
  expect(assigned.venue_stage_shape).toBe('thrust');

  // The venues page exposes the two shape selectors when editing.
  await page.goto('/venues');
  await page.getByText(name, { exact: true }).click();
  await expect(page.getByLabel('Footprint shape')).toBeVisible();
  await expect(page.getByLabel('Stage shape')).toBeVisible();
});

test('venue directory supports name search and exposes shape filters', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const arena = `E2E Search Arena ${Date.now()}`;
  const hall = `E2E Search Hall ${Date.now()}`;
  await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: {
      name: arena,
      venue_width_cm: 800,
      venue_height_cm: 600,
      footprint_shape: 'arena_circular',
      stage_shape: 'thrust',
    },
  });
  await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: {
      name: hall,
      venue_width_cm: 800,
      venue_height_cm: 600,
      footprint_shape: 'rectangular',
      stage_shape: 'proscenium',
    },
  });

  await page.goto('/venues');
  await expect(page.getByLabel('Footprint')).toBeVisible();
  await expect(page.getByLabel('Stage')).toBeVisible();

  const search = page.getByPlaceholder('Search venues by name');
  await search.fill(arena);
  await expect(page.getByText(arena, { exact: true })).toBeVisible();
  await expect(page.getByText(hall, { exact: true })).toHaveCount(0);

  await search.fill('');
  await expect(page.getByText(hall, { exact: true })).toBeVisible();
});
