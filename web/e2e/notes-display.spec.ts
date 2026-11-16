import { test, expect, APIRequestContext, Page } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

async function seed(page: Page, request: APIRequestContext) {
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  const headers = { Authorization: `Bearer ${token}` };
  const post = async (path: string, data: object) =>
    (await request.post(`${API_BASE}/api/v1${path}`, { headers, data })).json();
  const job = await post('/jobs', { title: `Notes MD ${Date.now()}` });
  // Short markdown: a bold lead-in.
  await post(`/jobs/${job.id}/graph/audio-devices`, {
    name: 'Short note device',
    device_type: 'other',
    notes: '**Heads up:** bring spare XLR.',
  });
  // Long markdown: a list plus enough paragraphs to overflow the collapsed (2-line) view.
  const longNote = [
    '## Patch notes',
    '- 4x XLR from stage left',
    '- 2x CAT6 to FOH',
    '',
    'Remember to label every cable at both ends before load-in.',
    'The rack lives stage right; keep the wireless rack away from the LED screens.',
    'Power is on the non-dimmed circuit. Do not plug the amp into dimmer power.',
  ].join('\n');
  await post(`/jobs/${job.id}/graph/audio-devices`, {
    name: 'Long note device',
    device_type: 'other',
    notes: longNote,
  });
  return job.id as string;
}

test('notes render markdown and respect a read-more toggle on phones', async ({ page, request }) => {
  // Sign in at the default desktop size: login() waits for the header's account button, whose
  // label is not shown on a phone (mirrors devices-inspect.spec.ts). Only then shrink to the
  // phone viewport (lt.sm -> list captions) so the list renders notes as captions.
  const jobId = await seed(page, request);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/jobs/${jobId}/workspace`);

  // Switch to the "All gear" list mode (q-tabs).
  await page.getByTestId('mode-toggle').getByText(/^(all gear|all utrustning)$/i).click();

  // Locate each note by its content rather than DOM order: the device list order is not
  // guaranteed, so nth()/first() can pick the wrong device in CI (the local pass was luck).
  // The short note renders markdown (bold -> <strong>) rather than raw text.
  const short = page.getByTestId('notes-display').filter({ hasText: 'Heads up' }).first();
  await expect(short).toBeVisible();
  const shortHtml = await short.innerHTML();
  expect(shortHtml).toContain('<strong>Heads up:</strong>');

  // The long note also renders markdown (a heading + a list).
  const long = page.getByTestId('notes-display').filter({ hasText: 'Patch notes' }).first();
  await expect(long).toBeVisible();
  const longHtml = await long.innerHTML();
  expect(longHtml).toContain('<h2');
  expect(longHtml).toContain('<li>');

  // Long note overflows the collapsed view -> a "read more" toggle appears; expanding it
  // keeps the rendered content and swaps to "read less".
  const readMore = page.getByTestId('notes-read-more');
  await expect(readMore).toBeVisible();
  await readMore.click();
  await expect(page.getByTestId('notes-read-less')).toBeVisible();
});
