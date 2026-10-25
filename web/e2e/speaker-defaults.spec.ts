import { test, expect } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

test('a speaker added from the palette points down the stage plot', async ({ page, request }) => {
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  const headers = { Authorization: `Bearer ${token}` };

  const created = await request.post(`${API_BASE}/api/v1/jobs`, {
    headers,
    data: { title: `E2E Speaker Default ${Date.now()}` },
  });
  const jobId = (await created.json()).id as string;

  await page.goto(`/jobs/${jobId}/stage-plot`);
  await page.getByText('Main speaker', { exact: true }).click();

  await expect
    .poll(async () => {
      const res = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, { headers });
      const elements = (await res.json()) as Array<{ element_type: string; rotation: number }>;
      return elements.find((e) => e.element_type === 'speaker_main')?.rotation;
    })
    .toBe(180);
});
