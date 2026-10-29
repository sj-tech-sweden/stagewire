import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

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

test('the stage plot exposes the outlet palette item and the power-nodes toggle', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Power UI ${Date.now()}` })).id as string;

  await page.goto(`/jobs/${jobId}/stage-plot`);
  await page.waitForLoadState('networkidle');

  // The outlet is now reachable from the palette, like the other plot objects.
  await expect(page.getByText('Add outlet', { exact: true }).first()).toBeVisible();
  // Power nodes draw on the plot as a graph, toggled separately from cables.
  await expect(page.getByText('Power nodes', { exact: true })).toBeVisible();
});

test('a merged feed is shown on a power node in the rigging panel', async ({
  page,
  request,
}) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (await post(request, headers, '/jobs', { title: `E2E Merge ${Date.now()}` })).id as string;

  const source = await post(request, headers, `/jobs/${jobId}/power-nodes`, {
    name: 'Mains',
    kind: 'source',
    feed_connector: 'cee32_3p',
    outputs: [{ connector: 'cee32_3p', count: 2 }],
  });
  const d1 = await post(request, headers, `/jobs/${jobId}/power-nodes`, {
    name: 'Distro A',
    kind: 'distro',
    parent_id: source.id,
    feed_connector: 'cee32_3p',
    outputs: [{ connector: 'schuko', count: 4 }],
  });
  const d2 = await post(request, headers, `/jobs/${jobId}/power-nodes`, {
    name: 'Distro B',
    kind: 'distro',
    parent_id: source.id,
    feed_connector: 'cee32_3p',
    outputs: [{ connector: 'schuko', count: 4 }],
  });
  // The merge (a second parent into the same node) is created through the API;
  // the rigging panel must render it as an extra feed on Distro A.
  const feed = await post(
    request,
    headers,
    `/jobs/${jobId}/power-nodes/${d1.id}/feeds`,
    { parent_id: d2.id, feed_connector: 'schuko' },
  );
  expect(feed.parent_id).toBe(d2.id);

  await page.goto(`/jobs/${jobId}?view=rigging`);
  await expect(page.getByText('Distro A', { exact: false }).first()).toBeVisible();

  // Open the edit dialog for Distro A and check the merged feed is listed.
  const row = page.locator('.row.items-center', { hasText: 'Distro A' }).first();
  await row.getByRole('button', { name: 'Edit', exact: true }).click();
  const editDialog = page.locator('.q-dialog');
  await expect(editDialog.getByText('Merged feeds', { exact: true })).toBeVisible();
  await expect(editDialog.getByText('Distro B', { exact: false }).first()).toBeVisible();

  // The merged feed can be removed again from the panel.
  await editDialog.getByRole('button', { name: 'Delete', exact: true }).first().click();
  await expect
    .poll(async () => {
      const nodes = await (
        await request.get(`${API_BASE}/api/v1/jobs/${jobId}/power-nodes`, { headers })
      ).json();
      const a = nodes.find((n: { id: string }) => n.id === d1.id);
      return a?.feeds?.length ?? 0;
    })
    .toBe(0);
});
