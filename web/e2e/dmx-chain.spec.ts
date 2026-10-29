import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

async function post(request: APIRequestContext, headers: Record<string, string>, path: string, data: object) {
  const res = await request.post(`${API_BASE}/api/v1${path}`, { headers, data });
  expect(res.status(), `${path}: ${await res.text()}`).toBeLessThan(300);
  return res.json();
}

async function selectOption(page: Page, label: string, option: string) {
  await page.getByLabel(label).click();
  await page.getByRole('option', { name: option, exact: true }).click();
}

test('a DMX universe and its chain of steps can be built on the lights page', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E DMX Chain ${Date.now()}` })).id as string;

  const consoleDevice = await post(request, headers, `/jobs/${jobId}/devices`, {
    name: 'Console',
    device_type: 'mixer',
  });
  const robin = await post(request, headers, `/jobs/${jobId}/devices`, {
    name: 'Robin',
    device_type: 'fixture',
  });
  await post(request, headers, `/jobs/${jobId}/fixtures`, {
    device_name: 'Robin',
    universe: 1,
    dmx_address: 1,
    footprint: 8,
  });

  await page.goto(`/jobs/${jobId}?view=lights`);
  page.on('dialog', (d) => d.accept());
  await expect(page.getByText('DMX chain', { exact: true })).toBeVisible();

  // Add a universe fed from the console.
  await page.getByRole('button', { name: 'Add universe' }).click();
  await page.getByLabel('Universe number').fill('1');
  await selectOption(page, 'Source device', 'Console');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  const uniCard = page.locator('.q-card', { hasText: 'Uni 1' });
  await expect(uniCard).toBeVisible();

  // Add a fixture step from the source.
  await uniCard.getByRole('button', { name: 'Add step', exact: true }).click();
  await selectOption(page, 'Fixture', 'Robin');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(uniCard).toContainText('Robin');

  // Add a device step branching from the fixture (its "Add step under" button).
  await uniCard.getByRole('button', { name: 'Add step under' }).click();
  await page.getByRole('button', { name: 'Device', exact: true }).click();
  await selectOption(page, 'Device', 'Console');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(uniCard).toContainText('Console');

  // Wait for the chain to be persisted and nested (the Save click's request is async).
  await expect
    .poll(async () => {
      const u = await (
        await request.get(`${API_BASE}/api/v1/jobs/${jobId}/dmx-universes`, { headers })
      ).json();
      return u[0]?.steps?.[0]?.children?.length ?? 0;
    })
    .toBe(1);

  // The API reflects the tree: fixture -> device.
  const universes = await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/dmx-universes`, { headers })).json();
  expect(universes).toHaveLength(1);
  expect(universes[0].steps).toHaveLength(1);
  expect(universes[0].steps[0].children).toHaveLength(1);

  // A step can be deleted (the device branch).
  uniCard
    .locator('.dmx-flow-node', { hasText: 'Console' })
    .getByRole('button', { name: 'Delete step' })
    .click();
  await expect
    .poll(async () => {
      const u = await (
        await request.get(`${API_BASE}/api/v1/jobs/${jobId}/dmx-universes`, { headers })
      ).json();
      return u[0]?.steps?.[0]?.children?.length ?? -1;
    })
    .toBe(0);
  await expect(uniCard).toContainText('Robin');
});

test('a fixture already in the chain is hidden from the add-step picker', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E DMX Hide ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Console', device_type: 'mixer' });
  await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Robin', device_type: 'fixture' });
  await post(request, headers, `/jobs/${jobId}/devices`, { name: 'LED', device_type: 'fixture' });
  await post(request, headers, `/jobs/${jobId}/fixtures`, { device_name: 'Robin', dmx_address: 1, footprint: 8 });
  await post(request, headers, `/jobs/${jobId}/fixtures`, { device_name: 'LED', dmx_address: 10, footprint: 8 });

  await page.goto(`/jobs/${jobId}?view=lights`);
  page.on('dialog', (d) => d.accept());
  await expect(page.getByText('DMX chain', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Add universe' }).click();
  await page.getByLabel('Universe number').fill('1');
  await selectOption(page, 'Source device', 'Console');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  const uniCard = page.locator('.q-card', { hasText: 'Uni 1' });
  await expect(uniCard).toBeVisible();

  await uniCard.getByRole('button', { name: 'Add step', exact: true }).click();
  await selectOption(page, 'Fixture', 'Robin');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(uniCard).toContainText('Robin');

  // Reopen the add-step dialog: Robin must no longer be offered, LED still is.
  await uniCard.getByRole('button', { name: 'Add step', exact: true }).click();
  await page.getByLabel('Fixture').click();
  await expect(page.getByRole('option', { name: 'Robin', exact: true })).toHaveCount(0);
  await expect(page.getByRole('option', { name: 'LED', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
});

test('adding a fixture step links the fixture to the universe', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E DMX Uni ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Console', device_type: 'mixer' });
  await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Robin', device_type: 'fixture' });
  await post(request, headers, `/jobs/${jobId}/fixtures`, { device_name: 'Robin', dmx_address: 1, footprint: 8 });

  await page.goto(`/jobs/${jobId}?view=lights`);
  page.on('dialog', (d) => d.accept());
  await expect(page.getByText('DMX chain', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Add universe' }).click();
  await page.getByLabel('Universe number').fill('1');
  await selectOption(page, 'Source device', 'Console');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  const uniCard = page.locator('.q-card', { hasText: 'Uni 1' });

  await uniCard.getByRole('button', { name: 'Add step', exact: true }).click();
  await selectOption(page, 'Fixture', 'Robin');
  await page.getByRole('button', { name: 'Save', exact: true }).click();

  // The fixture patch is async after the Save click, so poll the API.
  await expect
    .poll(async () => {
      const fixtures = await (
        await request.get(`${API_BASE}/api/v1/jobs/${jobId}/fixtures`, { headers })
      ).json();
      return fixtures.find((f: { device_name: string }) => f.device_name === 'Robin')?.universe ?? null;
    })
    .toBe(1);
});

test('a device can be created inline from the add step', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E DMX Inline ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Console', device_type: 'mixer' });

  await page.goto(`/jobs/${jobId}?view=lights`);
  page.on('dialog', (d) => d.accept());
  await expect(page.getByText('DMX chain', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Add universe' }).click();
  await page.getByLabel('Universe number').fill('1');
  await selectOption(page, 'Source device', 'Console');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  const uniCard = page.locator('.q-card', { hasText: 'Uni 1' });

  await uniCard.getByRole('button', { name: 'Add step', exact: true }).click();
  await page.getByRole('button', { name: 'Device', exact: true }).click();
  await page.getByRole('button', { name: 'Create device' }).click();
  await page.getByLabel('Device name').fill('Split 1');
  await page.getByLabel('Type').fill('split');
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await page.getByRole('button', { name: 'Save', exact: true }).click();

  await expect
    .poll(async () => {
      const devices = await (
        await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, { headers })
      ).json();
      return devices.find((d: { name: string }) => d.name === 'Split 1')?.device_type ?? null;
    })
    .toBe('split');
});

test('the DMX flow is drawn as a node-and-line diagram', async ({ page, request }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E DMX Diagram ${Date.now()}` })).id as string;
  await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Console', device_type: 'mixer' });
  await post(request, headers, `/jobs/${jobId}/devices`, { name: 'Robin', device_type: 'fixture' });
  await post(request, headers, `/jobs/${jobId}/fixtures`, { device_name: 'Robin', dmx_address: 1, footprint: 8 });

  await page.goto(`/jobs/${jobId}?view=lights`);
  page.on('dialog', (d) => d.accept());
  await expect(page.getByText('DMX chain', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Add universe' }).click();
  await page.getByLabel('Universe number').fill('1');
  await selectOption(page, 'Source device', 'Console');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  const uniCard = page.locator('.q-card', { hasText: 'Uni 1' });

  await uniCard.getByRole('button', { name: 'Add step', exact: true }).click();
  await selectOption(page, 'Fixture', 'Robin');
  await page.getByRole('button', { name: 'Save', exact: true }).click();

  // Add a device step under Robin so the diagram draws a connecting arrow.
  await uniCard.getByRole('button', { name: 'Add step under', exact: true }).click();
  await page.getByRole('button', { name: 'Device', exact: true }).click();
  await selectOption(page, 'Device', 'Console');
  await page.getByRole('button', { name: 'Save', exact: true }).click();

  const diagram = uniCard.locator('.dmx-flow');
  await expect(diagram).toBeVisible();
  await expect(diagram).toContainText('Robin');
  await expect(diagram.locator('.dmx-flow-node')).toHaveCount(2);
  await expect(uniCard.locator('svg.dmx-flow-arrows line')).not.toHaveCount(0);
});
