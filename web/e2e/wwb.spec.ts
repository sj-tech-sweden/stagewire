import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';
import { resolve } from 'path';

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

async function seedListWithWirelessChannel(
  request: APIRequestContext,
  headers: Record<string, string>,
  sourceLabel: string,
) {
  const jobId = (await post(request, headers, '/jobs', { title: `WWB E2E ${Date.now()}` })).id as string;
  const list = await post(request, headers, `/jobs/${jobId}/channel-lists`, { name: 'FOH' });
  const channel = await post(
    request,
    headers,
    `/jobs/${jobId}/channel-lists/${list.id}/channels`,
    {
      channel_number: 1,
      source_label: sourceLabel,
      input_type: 'wireless',
      wireless_pack: 'Shure SLXD4D',
    },
  );
  return { jobId, listId: list.id as string, channelId: channel.id as string };
}

async function getChannel(
  request: APIRequestContext,
  headers: Record<string, string>,
  jobId: string,
  listId: string,
  channelId: string,
) {
  const res = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/channel-lists/${listId}/channels`, {
    headers,
  });
  expect(res.status()).toBeLessThan(300);
  const rows = (await res.json()) as Array<Record<string, unknown>>;
  return rows.find((c) => c.id === channelId);
}

// A .shw whose channel name matches the Stagewire channel by name is auto-suggested;
// confirming imports the coordinated frequency into the matched channel.
test('wireless workbench file auto-matches by name and imports the frequency', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId, channelId } = await seedListWithWirelessChannel(request, headers, 'Vox');

  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  await page.getByTestId('import-wwb').waitFor();

  await page.getByTestId('wwb-file').setInputFiles(resolve(__dirname, 'fixtures/wwb_vox.shw'));

  const row = page.getByTestId('wwb-map-row').first();
  await row.waitFor();
  // The matching channel is pre-selected by name, so the select already has a value.
  await expect(page.getByTestId('wwb-map-select-0')).not.toHaveValue('');
  await page.getByTestId('wwb-map-confirm').click();

  const channel = await getChannel(request, headers, jobId, listId, channelId);
  expect(channel?.wireless_frequency_mhz).toBe(559.825);
});

// A .shw whose channel name does NOT match is left unmatched; the user picks the
// Stagewire channel manually in the mapping dialog before importing.
test('wireless workbench file can be mapped manually when names differ', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const { jobId, listId, channelId } = await seedListWithWirelessChannel(request, headers, 'Vox');

  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  await page.getByTestId('import-wwb').waitFor();

  await page.getByTestId('wwb-file').setInputFiles(resolve(__dirname, 'fixtures/wwb_mica.shw'));

  const row = page.getByTestId('wwb-map-row').first();
  await row.waitFor();
  // No name match, so the select starts empty.
  await expect(page.getByTestId('wwb-map-select-0')).toHaveValue('');

  await page.getByTestId('wwb-map-select-0').click();
  await page.getByRole('option', { name: /Vox/ }).click();
  await page.getByTestId('wwb-map-confirm').click();

  const channel = await getChannel(request, headers, jobId, listId, channelId);
  expect(channel?.wireless_frequency_mhz).toBe(606.25);
});
