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
  uniCard.getByRole('button', { name: 'Delete step' }).nth(1).click();
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
