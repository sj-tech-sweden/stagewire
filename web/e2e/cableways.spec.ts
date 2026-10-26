import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function authedHeaders(page: Page) {
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  return { Authorization: `Bearer ${token}` };
}

test('an existing cableway can be edited in place', async ({ page, request }: { page: Page; request: APIRequestContext }) => {
  await login(page);
  const headers = await authedHeaders(page);
  const jobId = (
    await (
      await request.post(`${API_BASE}/api/v1/jobs`, {
        headers,
        data: { title: `E2E Cableway ${Date.now()}`, stage_width_cm: 600, stage_height_cm: 400 },
      })
    ).json()
  ).id as string;
  await request.patch(`${API_BASE}/api/v1/jobs/${jobId}`, {
    headers,
    data: {
      cable_plan: {
        cableways: [{ id: 'way-1', points: [[0, 300], [400, 300]] }],
        routes: {},
        settings: {},
      },
    },
  });

  await page.goto(`/jobs/${jobId}/stage-plot`);
  await page.getByRole('button', { name: 'Edit', exact: true }).click();
  await page.locator('canvas').first().click({ position: { x: 200, y: 60 } });
  await page.getByRole('button', { name: 'Save cableway' }).click();

  await expect
    .poll(async () => {
      const res = await request.get(`${API_BASE}/api/v1/jobs/${jobId}`, { headers });
      const plan = (await res.json()).cable_plan;
      return plan.cableways.map((w: { id: string; points: unknown[] }) => [w.id, w.points.length]);
    })
    .toEqual([['way-1', 3]]);
});
