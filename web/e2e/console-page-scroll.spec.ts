import { test, expect, APIRequestContext, Page, Locator } from '@playwright/test';
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

// True when the element, or anything inside it, is a vertical scroll container that actually
// overflows. The console's lists used to sit in a fixed-height window with their own scrollbar
// (input table 70vh, soft patch list 30vh, grid 38vh); they now grow and the page scrolls.
async function hasInnerVerticalScroll(locator: Locator) {
  return locator.evaluate((root) => {
    const all = [root as HTMLElement, ...Array.from(root.querySelectorAll<HTMLElement>('*'))];
    return all.some((el) => {
      const overflowY = getComputedStyle(el).overflowY;
      return (overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 1;
    });
  });
}

async function seedLongList(page: Page, request: APIRequestContext, count: number) {
  await login(page);
  const headers = await authedHeaders(page);
  const job = await post(request, headers, '/jobs', { title: `Console scroll ${Date.now()}` });
  const list = await post(request, headers, `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  for (let n = 1; n <= count; n++) {
    await post(request, headers, `/jobs/${job.id}/channel-lists/${list.id}/channels`, {
      channel_number: n,
      source_label: `Src ${n}`,
    });
  }
  return job.id as string;
}

test('a long input list grows with the page instead of scrolling in a window of its own', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 800 });
  const jobId = await seedLongList(page, request, 60);
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  await page.getByTestId('console-tab-inputs').click();
  const table = page.getByTestId('channel-table');
  await expect(table).toBeVisible();
  await expect(table.locator('tbody tr')).toHaveCount(60);
  // every row is in the page (no virtual window), so the table is taller than the screen ...
  const box = (await table.boundingBox())!;
  expect(box.height).toBeGreaterThan(800);
  // ... and nothing inside it scrolls on its own
  expect(await hasInnerVerticalScroll(table)).toBe(false);
  // the page itself is what scrolls
  const pageScrolls = await page.evaluate(() => document.documentElement.scrollHeight > window.innerHeight);
  expect(pageScrolls).toBe(true);
});

test('the soft patch grid and list grow with the page too', async ({ page, request }) => {
  await page.setViewportSize({ width: 1400, height: 800 });
  const jobId = await seedLongList(page, request, 120);
  await page.goto(`/jobs/${jobId}/workspace?view=lists`);
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-patch').click();
  const grid = page.getByTestId('console-patch-grid');
  await expect(grid).toBeVisible();
  expect(await hasInnerVerticalScroll(grid)).toBe(false);
  // the list view of the same strips behaves the same way
  await page.getByTestId('console-overview-view').getByRole('button').nth(1).click();
  const overview = page.getByTestId('console-patch-overview');
  await expect(overview).toBeVisible();
  await expect(page.getByTestId('console-patch-card')).toHaveCount(120);
  expect(await hasInnerVerticalScroll(overview)).toBe(false);
});
