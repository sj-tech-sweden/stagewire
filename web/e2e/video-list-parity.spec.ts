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
    devices: Array<{ id: string; kind: string; attributes: Record<string, unknown> }>;
  };
  return graph.devices;
}

async function openVideoList(page: Page, request: APIRequestContext) {
  await page.setViewportSize({ width: 1400, height: 900 });
  await login(page);
  const headers = await authedHeaders(page);
  const job = await post(request, headers, '/jobs', { title: `Video parity ${Date.now()}` });
  const list = await post(request, headers, `/jobs/${job.id}/graph/video-lists`, { name: 'Cams' });
  await page.goto(`/jobs/${job.id}/workspace?view=video`);
  await expect(page.getByTestId('video-video_input-table')).toBeVisible();
  return { jobId: job.id as string, listId: list.id as string };
}

test('bulk add creates many video inputs at once', async ({ page, request }) => {
  const { jobId, listId } = await openVideoList(page, request);

  // The list starts empty.
  expect(
    (await graphNodes(page, request, jobId)).filter((d) => d.kind === 'video_input' && d.attributes.list_id === listId)
      .length,
  ).toBe(0);

  await page.getByTestId('bulk-inputs').click();
  await expect(page.getByTestId('video-bulk-create')).toBeVisible();
  await page.getByTestId('video-bulk-count').fill('6');
  await page.getByTestId('video-bulk-prefix').fill('Cam');
  await page.getByTestId('video-bulk-create').click();

  await expect
    .poll(async () => {
      return (await graphNodes(page, request, jobId)).filter(
        (d) => d.kind === 'video_input' && d.attributes.list_id === listId,
      ).length;
    })
    .toBe(6);

  // Names follow the "Prefix N" convention and numbers continue from the start.
  const inputs = (await graphNodes(page, request, jobId)).filter(
    (d) => d.kind === 'video_input' && d.attributes.list_id === listId,
  );
  expect(inputs.some((d) => d.attributes.source_label === 'Cam 1')).toBe(true);
  expect(inputs.some((d) => d.attributes.source_label === 'Cam 6')).toBe(true);
});

test('bulk add creates many video outputs at once', async ({ page, request }) => {
  const { jobId, listId } = await openVideoList(page, request);

  await page.getByTestId('bulk-outputs').click();
  await expect(page.getByTestId('video-bulk-create')).toBeVisible();
  await page.getByTestId('video-bulk-count').fill('4');
  await page.getByTestId('video-bulk-prefix').fill('PGM');
  await page.getByTestId('video-bulk-create').click();

  await expect
    .poll(async () => {
      return (await graphNodes(page, request, jobId)).filter(
        (d) => d.kind === 'video_destination' && d.attributes.list_id === listId,
      ).length;
    })
    .toBe(4);
});

test('the set-switcher button opens the switcher dialog', async ({ page, request }) => {
  await openVideoList(page, request);
  await page.getByTestId('set-switcher').click();
  await expect(page.getByTestId('switcher-dialog')).toBeVisible();
  await expect(page.getByTestId('switcher-picker')).toBeVisible();
  await expect(page.getByTestId('switcher-inputs')).toBeVisible();
  await expect(page.getByTestId('switcher-outputs')).toBeVisible();
});

test('setting a manual switcher fills the list to its size', async ({ page, request }) => {
  const { jobId, listId } = await openVideoList(page, request);

  // No rows before setting a switcher.
  expect(
    (await graphNodes(page, request, jobId)).filter((d) => d.kind === 'video_input' && d.attributes.list_id === listId)
      .length,
  ).toBe(0);

  await page.getByTestId('set-switcher').click();
  await page.getByTestId('switcher-inputs').fill('3');
  await page.getByTestId('switcher-outputs').fill('2');
  await page.getByTestId('switcher-save').click();

  // Mirrors the sound mixer: setting a switcher pads the list to its size.
  await expect
    .poll(async () => {
      const nodes = await graphNodes(page, request, jobId);
      return {
        inputs: nodes.filter((d) => d.kind === 'video_input' && d.attributes.list_id === listId).length,
        outputs: nodes.filter((d) => d.kind === 'video_destination' && d.attributes.list_id === listId).length,
      };
    })
    .toEqual({ inputs: 3, outputs: 2 });

  // The summary and the (now reachable) fill action show for a manually-set switcher.
  await expect(page.getByTestId('fill-from-switcher')).toBeVisible();
});
