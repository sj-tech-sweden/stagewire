import { test, expect } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

test('create a job and manage channel lists', async ({ page, request }) => {
  await login(page);

  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  const authHeaders = { Authorization: `Bearer ${token}` };
  const title = `E2E Show ${Date.now()}`;
  const created = await request.post(`${API_BASE}/api/v1/jobs`, {
    headers: authHeaders,
    data: { title, venue_name: 'E2E Hall' },
  });
  const jobId = (await created.json()).id;
  const performerPlotElement = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, {
    headers: authHeaders,
    data: {
      element_type: 'performer',
      label: 'Alex Singer',
    },
  });
  expect(performerPlotElement.status()).toBe(201);

  // Open the job detail page
  await page.goto(`/jobs/${jobId}`);
  await expect(page).toHaveURL(/\/jobs\//);
  await expect(page.locator('.text-h5')).toContainText(title);

  // Add a channel list via the dialog
  await page.getByRole('button', { name: /add list/i }).click();
  const listDialog = page.locator('.q-dialog');
  await listDialog.locator('input').first().fill('FOH');
  await listDialog.getByRole('button', { name: /save/i }).click();
  await expect(page.locator('.q-item', { hasText: 'FOH' }).first()).toBeVisible();

  // Add a channel to the list
  await page.getByRole('button', { name: /add channel/i }).click();
  const channelDialog = page.locator('.q-dialog');
  await channelDialog.locator('input').nth(0).fill('1');
  await channelDialog.locator('input').nth(1).fill('Lead vocal');
  await expect(channelDialog.getByLabel('Actor / presenter')).toBeVisible();
  await channelDialog.getByLabel('Link to stage-plot person').click();
  await page.getByRole('option', { name: 'Alex Singer', exact: true }).click();
  await channelDialog.getByLabel('Type').click();
  await page.getByRole('option', { name: 'Wireless', exact: true }).click();
  await channelDialog.getByLabel('Instrument group').click();
  await page.getByRole('option', { name: 'Vocals', exact: true }).click();
  await channelDialog.getByLabel('Bodypack / beltpack').fill('Beltpack 2');
  await channelDialog.getByLabel('Wireless frequency').fill('518.125 MHz');
  await channelDialog.getByRole('button', { name: /save/i }).click();

  // Save is async; wait for the dialog to close, then the row appears.
  await expect(page.locator('.q-dialog')).toHaveCount(0);
  await expect(page.locator('table').first().getByRole('textbox')).toHaveValue('Lead vocal');
  await expect(page.getByText('Alex Singer · Beltpack 2 · 518.125 MHz')).toBeVisible();

  const channelRow = page.getByRole('row').filter({ hasText: 'Lead vocal' });
  await channelRow.getByRole('button', { name: 'Edit channel' }).click();
  const editChannelDialog = page.locator('.q-dialog');
  await editChannelDialog.getByLabel('Actor / presenter').fill('Alex Updated');
  await editChannelDialog.getByRole('button', { name: /save/i }).click();
  await expect(page.locator('.q-dialog')).toHaveCount(0);
  await expect(page.getByText('Alex Updated · Beltpack 2 · 518.125 MHz')).toBeVisible();

  const listsRes = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists`, {
    headers: authHeaders,
  });
  const channels = (await listsRes.json())[0].channels;
  const channel = channels[0];
  expect(channel.instrument_group).toBe('vocals');
  expect(channel.performer_name).toBe('Alex Updated');
  expect(channel.wireless_pack).toBe('Beltpack 2');
  expect(channel.wireless_frequency).toBe('518.125 MHz');
  const plotElementsRes = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, {
    headers: authHeaders,
  });
  const plotElements = await plotElementsRes.json();
  expect(
    plotElements.find((element) => element.id === performerPlotElement.json().id).linked_channel_id,
  ).toBe(channel.id);
  expect(
    plotElements.find((element) => element.id === performerPlotElement.json().id).label,
  ).toBe('Alex Updated');

  const linkedElement = await request.post(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, {
    headers: authHeaders,
    data: {
      element_type: 'wireless_receiver',
      label: 'Wireless RX',
      linked_channel_id: channel.id,
    },
  });
  expect(linkedElement.status()).toBe(201);
  await page.reload();
  await expect(page.getByText('Wireless RX', { exact: true })).toBeVisible();

  // A new channel's default patch point must auto-link to a Mixer device, so the
  // mandatory device-linking validation does not block the save (regression test).
  const devicesRes = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/devices`, {
    headers: authHeaders,
  });
  const devices = (await devicesRes.json()) as Array<{ device_type?: string }>;
  expect(devices.some((d) => d.device_type === 'mixer')).toBe(true);
});
