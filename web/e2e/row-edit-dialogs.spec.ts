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

async function graphNodes(page: Page, request: APIRequestContext, jobId: string) {
  const headers = await authedHeaders(page);
  const graph = (await (await request.get(`${API_BASE}/api/v1/jobs/${jobId}/graph`, { headers })).json()) as {
    devices: Array<{ id: string; attributes: Record<string, unknown> }>;
  };
  return graph.devices;
}

async function openChannelList(page: Page, request: APIRequestContext) {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const job = await post(request, headers, '/jobs', { title: `Row dialogs ${Date.now()}` });
  const list = await post(request, headers, `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  const first = await post(request, headers, `/jobs/${job.id}/channel-lists/${list.id}/channels`, {
    channel_number: 1,
    source_label: 'Lead vocal',
  });
  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await expect(page.getByTestId('channel-table')).toBeVisible();
  return { jobId: job.id as string, channelId: first.id as string };
}

async function openVideoList(page: Page, request: APIRequestContext) {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const job = await post(request, headers, '/jobs', { title: `Video dialogs ${Date.now()}` });
  const list = await post(request, headers, `/jobs/${job.id}/graph/video-lists`, { name: 'Cams' });
  const input = await post(request, headers, `/jobs/${job.id}/graph/video-lists/${list.id}/inputs`, {
    source_label: 'Cam 1',
  });
  const output = await post(request, headers, `/jobs/${job.id}/graph/video-lists/${list.id}/outputs`, {
    name: 'PGM',
  });
  await page.goto(`/jobs/${job.id}/workspace?view=video`);
  await expect(page.getByTestId('video-input-table')).toBeVisible();
  return {
    jobId: job.id as string,
    inputId: input.id as string,
    outputId: output.id as string,
  };
}

test('the channel edit dialog exposes the full attribute set and saves it', async ({ page, request }) => {
  const { jobId, channelId } = await openChannelList(page, request);

  await page.getByTestId('channel-edit-open').first().click();
  await expect(page.getByTestId('channel-edit-dialog')).toBeVisible();
  // the full field set lives in the dialog, not only the inline table
  await expect(page.getByTestId('channel-edit-name')).toBeVisible();
  await expect(page.getByTestId('channel-edit-kind')).toBeVisible();
  await expect(page.getByTestId('channel-edit-group')).toBeVisible();
  await expect(page.getByTestId('channel-edit-performer')).toBeVisible();
  await expect(page.getByTestId('channel-edit-phantom')).toBeVisible();
  await expect(page.getByTestId('channel-edit-stereo')).toBeVisible();
  await expect(page.getByTestId('channel-edit-notes')).toBeVisible();

  // switching the kind to Wireless reveals the wireless block
  await page.getByTestId('channel-edit-kind').click();
  await page.getByRole('option', { name: 'Wireless' }).click();
  await expect(page.getByTestId('channel-edit-wireless-pack')).toBeVisible();
  await page.getByTestId('channel-edit-wireless-pack').fill('ADX1');
  // switch back to a non-wireless kind so the wireless block collapses again
  await page.getByTestId('channel-edit-kind').click();
  await page.getByRole('option', { name: 'Microphone' }).click();

  await page.getByTestId('channel-edit-performer').fill('Anna');
  await page.getByTestId('channel-edit-phantom').click();
  await page.getByTestId('channel-edit-group').click();
  await page.getByRole('option', { name: 'Vocals' }).click();
  await page.getByTestId('channel-edit-save').click();

  await expect
    .poll(async () => {
      const node = (await graphNodes(page, request, jobId)).find((d) => d.id === channelId)!;
      return {
        performer: node.attributes.performer_name,
        phantom: node.attributes.phantom_power,
        group: node.attributes.instrument_group,
      };
    })
    .toEqual({ performer: 'Anna', phantom: true, group: 'vocals' });
});

test('the video row edit dialog exposes signal metadata and saves it', async ({ page, request }) => {
  const { jobId, inputId, outputId } = await openVideoList(page, request);

  // Input row: source, connector and the new signal fields.
  await page.getByTestId('video-edit-open').first().click();
  await expect(page.getByTestId('video-edit-dialog')).toBeVisible();
  await expect(page.getByTestId('video-edit-name')).toBeVisible();
  await expect(page.getByTestId('video-edit-source-type')).toBeVisible();
  await expect(page.getByTestId('video-edit-connector')).toBeVisible();
  await expect(page.getByTestId('video-edit-resolution')).toBeVisible();
  await expect(page.getByTestId('video-edit-frame-rate')).toBeVisible();
  await expect(page.getByTestId('video-edit-signal-format')).toBeVisible();
  await expect(page.getByTestId('video-edit-color-space')).toBeVisible();
  await expect(page.getByTestId('video-edit-aspect-ratio')).toBeVisible();

  await page.getByTestId('video-edit-resolution').fill('1920x1080');
  await page.getByTestId('video-edit-frame-rate').fill('50i');
  await page.getByTestId('video-edit-signal-format').click();
  await page.getByRole('option', { name: 'NDI' }).click();
  await page.getByTestId('video-edit-color-space').click();
  await page.getByRole('option', { name: 'Rec2020' }).click();
  await page.getByTestId('video-edit-aspect-ratio').fill('16:9');
  await page.getByTestId('video-edit-save').click();

  await expect
    .poll(async () => {
      const node = (await graphNodes(page, request, jobId)).find((d) => d.id === inputId)!;
      return {
        resolution: node.attributes.resolution,
        frame_rate: node.attributes.frame_rate,
        signal_format: node.attributes.signal_format,
        color_space: node.attributes.color_space,
        aspect_ratio: node.attributes.aspect_ratio,
      };
    })
    .toEqual({
      resolution: '1920x1080',
      frame_rate: '50i',
      signal_format: 'NDI',
      color_space: 'Rec2020',
      aspect_ratio: '16:9',
    });

  // Output row shares the same dialog and the same signal fields.
  await page.getByTestId('video-edit-open').nth(1).click();
  await expect(page.getByTestId('video-edit-dialog')).toBeVisible();
  await page.getByTestId('video-edit-resolution').fill('3840x2160');
  await page.getByTestId('video-edit-signal-format').click();
  await page.getByRole('option', { name: 'ST2110' }).click();
  await page.getByTestId('video-edit-save').click();

  await expect
    .poll(async () => {
      const node = (await graphNodes(page, request, jobId)).find((d) => d.id === outputId)!;
      return { resolution: node.attributes.resolution, signal_format: node.attributes.signal_format };
    })
    .toEqual({ resolution: '3840x2160', signal_format: 'ST2110' });
});
