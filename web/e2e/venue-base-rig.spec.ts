import { test, expect, Page, APIRequestContext } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';
import { resolve } from 'path';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

async function createJob(request: APIRequestContext, headers: Record<string, string>) {
  const res = await request.post(`${API_BASE}/api/v1/jobs`, {
    headers,
    data: { title: `E2E Base Rig Job ${Date.now()}` },
  });
  expect(res.ok()).toBeTruthy();
  return (await res.json()).id as string;
}

test('venue base rig can be edited on the canvas and persists', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);

  const venueRes = await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: { name: `E2E Base Rig ${Date.now()}`, venue_width_cm: 800, venue_height_cm: 600 },
  });
  expect(venueRes.status()).toBe(201);
  const venue = await venueRes.json();

  await page.goto(`/venues/${venue.id}/base-rig`);
  await expect(page.getByText('No devices yet')).toBeVisible();

  // Seed one device through the "Add gear" dropdown. The rig canvas is a Konva surface (a device
  // can't be picked by clicking its label), so select it from the "All gear" DOM table, then rename
  // it in the inspector card on the Stage (canvas) tab. Edits commit immediately through the
  // incremental graph route (no separate "Save" step). The card's name input is matched by its current
  // value because Quasar q-inputs expose that as the input's value attribute but not as a form-field
  // accessible name.
  await page.getByRole('button', { name: 'Add gear' }).click();
  await page.getByTestId('add-gear-speaker_main').click();
  await page.getByRole('tab', { name: 'All gear' }).click();
  const mainRow = page
    .getByTestId('workspace-table')
    .locator('tr')
    .filter({ has: page.locator('input[value="Main speaker"]') });
  // Click a non-name cell (the name cell stops propagation so it keeps edit focus) to select the row.
  await mainRow.locator('td').nth(1).click();
  await page.getByRole('tab', { name: 'Stage' }).click();
  const nameInput = page.locator('input[value="Main speaker"]');
  await expect(nameInput).toBeVisible();
  await nameInput.fill('House L/R');
  // Edits commit immediately through the incremental graph route (no separate "Save" step), so the
  // rig is already stored venue-owned. The PATCH is fire-and-forget from the input handler, so poll
  // the API until the rename has actually landed rather than reading it race-prone right after fill().
  await expect
    .poll(async () => {
      const g = await (await request.get(`${API_BASE}/api/v1/venues/${venue.id}/graph`, { headers })).json();
      return g.devices.map((d: { name: string }) => d.name);
    })
    .toEqual(['House L/R']);

  // It persists across a reload: the renamed device shows up in the "All gear" table.
  await page.reload();
  await page.getByRole('tab', { name: 'All gear' }).click();
  await expect(page.locator('input[value="House L/R"]')).toBeVisible();
});

test('assigning a venue clones its base rig onto the job', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);

  const venueRes = await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: { name: `E2E Clone Rig ${Date.now()}`, venue_width_cm: 800, venue_height_cm: 600 },
  });
  const venue = await venueRes.json();

  await request.put(`${API_BASE}/api/v1/venues/${venue.id}/graph`, {
    headers,
    data: {
      devices: [
        {
          // A fresh id per run keeps the test idempotent: a fixed UUID would collide with the row
          // left behind by any previous run and trip the graph_devices primary-key constraint.
          id: crypto.randomUUID(),
          domain: 'audio',
          kind: 'speaker',
          name: 'House Stagebox',
          attributes: {},
          ports: [],
        },
      ],
      edges: [],
    },
  });

  const jobId = await createJob(request, headers);
  const assign = await request.put(`${API_BASE}/api/v1/jobs/${jobId}/venue`, {
    headers,
    data: { venue_id: venue.id },
  });
  expect(assign.ok()).toBeTruthy();

  const jobGraph = await (
    await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })
  ).json();
  expect(jobGraph.devices).toHaveLength(1);
  expect(jobGraph.devices[0].name).toBe('House Stagebox');
  expect(jobGraph.devices[0].venue_id).toBeNull();
});

test('venue fixture library is managed through the base rig and stays venue-scoped', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);

  const venueRes = await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: { name: `E2E Venue Lib ${Date.now()}`, venue_width_cm: 800, venue_height_cm: 600 },
  });
  expect(venueRes.status()).toBe(201);
  const venue = await venueRes.json();

  await page.goto(`/venues/${venue.id}/base-rig`);

  // Open the fixture library from the base rig header and add a type.
  await page.getByRole('button', { name: 'Fixture library' }).click();
  await expect(page.getByTestId('library-type-name')).toBeVisible();
  await page.getByTestId('library-type-name').fill('House Spot');
  await page.getByTestId('library-add-type').click();

  // It shows up in the dialog...
  await expect(page.getByTestId('library-type').filter({ hasText: 'House Spot' })).toBeVisible();

  // ...and is stored venue-owned (job_id null, venue_id set) via the venue endpoint.
  const types = await (
    await request.get(`${API_BASE}/api/v1/venues/${venue.id}/fixture-types`, { headers })
  ).json();
  expect(types).toHaveLength(1);
  expect(types[0].name).toBe('House Spot');
  expect(types[0].venue_id).toBe(venue.id);
  expect(types[0].job_id).toBeNull();

  // The same type never leaks into a separate job's library.
  const jobId = await createJob(request, headers);
  const jobTypes = await (
    await request.get(`${API_BASE}/api/v1/jobs/${jobId}/fixture-types`, { headers })
  ).json();
  expect(jobTypes).toHaveLength(0);
});

test('venue channel list reuses the editor and imports a Wireless Workbench file', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);

  // A venue owns its own channel list (and its wireless channels) via the venue graph routes.
  const venueRes = await request.post(`${API_BASE}/api/v1/venues`, {
    headers,
    data: { name: `E2E Venue Lists ${Date.now()}`, venue_width_cm: 800, venue_height_cm: 600 },
  });
  expect(venueRes.status()).toBe(201);
  const venue = await venueRes.json();

  const list = await (
    await request.post(`${API_BASE}/api/v1/venues/${venue.id}/graph/lists`, {
      headers,
      data: { name: 'House RF' },
    })
  ).json();
  await request.post(`${API_BASE}/api/v1/venues/${venue.id}/graph/lists/${list.id}/channels/batch`, {
    headers,
    data: [{ channel_number: 1, source_label: 'Vox', input_type: 'wireless' }],
  });

  // The list is stored venue-owned (job_id null, venue_id set).
  const rig = await (
    await request.get(`${API_BASE}/api/v1/venues/${venue.id}/graph`, { headers })
  ).json();
  const cl = rig.devices.find((d: { kind: string }) => d.kind === 'channel_list');
  expect(cl).toBeTruthy();
  expect(cl.job_id).toBeNull();
  expect(cl.venue_id).toBe(venue.id);

  // The same editor the jobs use drives the venue rig; the Wireless Workbench import lands the
  // coordinated frequency onto the venue's wireless channel.
  await page.goto(`/venues/${venue.id}/base-rig`);
  // The channel-list editor is reached via the "Channel lists" mode tab (the same editor the jobs use).
  await page.getByRole('tab', { name: 'Channel lists' }).click();
  await page.getByTestId('channel-list-editor').waitFor();

  await page.getByTestId('import-wwb').click();
  await page.getByTestId('wwb-file').setInputFiles(resolve(__dirname, 'fixtures/wwb_vox.shw'));
  const row = page.getByTestId('wwb-map-row').first();
  await row.waitFor();
  await page.getByTestId('wwb-map-confirm').click();
  await expect(page.getByTestId('wwb-map-confirm')).toBeHidden();

  const after = await (
    await request.get(`${API_BASE}/api/v1/venues/${venue.id}/graph`, { headers })
  ).json();
  // Channel-list channels are stored as graph devices with kind "channel"; their source label and the
  // imported frequency live in `attributes` (not top-level fields), so query by attributes.source_label.
  const channel = after.devices.find(
    (d: { kind: string; attributes?: { source_label?: string } }) =>
      d.kind === 'channel' && d.attributes?.source_label === 'Vox',
  );
  expect(channel?.attributes?.wireless_frequency_mhz).toBe(559.825);
});
