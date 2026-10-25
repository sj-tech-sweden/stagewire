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

test('the add-speakers dialog places a row of speakers', async ({ page, request }) => {
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  const headers = { Authorization: `Bearer ${token}` };
  const created = await request.post(`${API_BASE}/api/v1/jobs`, {
    headers,
    data: { title: `E2E Speaker Array ${Date.now()}`, stage_width_cm: 600, stage_height_cm: 400 },
  });
  const jobId = (await created.json()).id as string;

  await page.goto(`/jobs/${jobId}/stage-plot`);
  await page.getByText('Add speakers', { exact: true }).click();
  await page.getByLabel('How many').fill('4');
  await page.getByRole('button', { name: 'Add', exact: true }).click();

  await expect
    .poll(async () => {
      const res = await request.get(`${API_BASE}/api/v1/jobs/${jobId}/plot-elements`, { headers });
      const elements = (await res.json()) as Array<{ element_type: string; position_x: number }>;
      const xs = elements.filter((e) => e.element_type === 'speaker_main').map((e) => e.position_x);
      return new Set(xs).size;
    })
    .toBe(4);
});
