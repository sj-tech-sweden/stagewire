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

// A dialog card that is taller than the window used to scroll as a whole, so its action buttons
// ended up below the fold. The cards are now capped to the viewport and only their body scrolls:
// these checks pin that down on a short window with a long list.
async function expectFitsViewport(page: Page, card: ReturnType<Page['getByTestId']>, button: ReturnType<Page['getByTestId']>) {
  const viewport = page.viewportSize()!;
  const cardBox = (await card.boundingBox())!;
  expect(cardBox.y).toBeGreaterThanOrEqual(0);
  expect(cardBox.y + cardBox.height).toBeLessThanOrEqual(viewport.height);
  const buttonBox = (await button.boundingBox())!;
  expect(buttonBox.y + buttonBox.height).toBeLessThanOrEqual(viewport.height);
}

test('the auto patch dialog keeps its buttons in view with a long plan, and the body scrolls', async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 520 });
  await login(page);
  const headers = await authedHeaders(page);
  const job = await post(request, headers, '/jobs', { title: `Console dialogs ${Date.now()}` });
  const list = await post(request, headers, `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  for (let n = 1; n <= 40; n++) {
    await post(request, headers, `/jobs/${job.id}/channel-lists/${list.id}/channels`, {
      channel_number: n,
      source_label: `Src ${n}`,
    });
  }
  await post(request, headers, `/jobs/${job.id}/devices`, {
    name: 'AR4848',
    device_type: 'analog_stagebox',
    ports: [{ direction: 'in', connector: 'xlr3', count: 48 }],
  });
  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-patch').click();
  await page.getByTestId('console-select-all').click();
  await page.getByTestId('console-select-auto').click();
  const dialog = page.getByTestId('console-auto-dialog');
  await expect(dialog).toBeVisible();
  await page.getByTestId('console-auto-preview').click();
  await expect(page.getByTestId('console-auto-plan-row')).toHaveCount(40);

  await expectFitsViewport(page, dialog, page.getByTestId('console-auto-apply'));
  // the plan is longer than the card, so it is the body that scrolls, not the whole dialog
  const scrolls = await dialog
    .locator('.console-dialog-body')
    .evaluate((el) => el.scrollHeight > el.clientHeight);
  expect(scrolls).toBe(true);
});

test('the manual console form keeps Save in view on a short window', async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 480 });
  await login(page);
  const headers = await authedHeaders(page);
  const job = await post(request, headers, '/jobs', { title: `Console form ${Date.now()}` });
  await post(request, headers, `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-profile').click();
  await page.getByTestId('console-manual').click();
  const form = page.getByTestId('console-manual-form');
  await expect(form).toBeVisible();
  await expectFitsViewport(page, page.locator('.console-dialog'), page.getByTestId('console-form-save'));
});

test('on a phone the console dialogs fill the screen and keep their buttons reachable', async ({ page, request }) => {
  // sign in at the default size: login() waits for the account button, whose label is hidden on a phone
  await login(page);
  const headers = await authedHeaders(page);
  const job = await post(request, headers, '/jobs', { title: `Console phone ${Date.now()}` });
  await post(request, headers, `/jobs/${job.id}/channel-lists`, { name: 'FOH' });
  await page.setViewportSize({ width: 390, height: 640 });
  await page.goto(`/jobs/${job.id}/workspace?view=lists`);
  await expect(page.getByTestId('console-panel')).toBeVisible();
  await page.getByTestId('console-tab-profile').click();
  await page.getByTestId('console-manual').click();
  await expect(page.getByTestId('console-manual-form')).toBeVisible();
  await expectFitsViewport(page, page.locator('.console-dialog'), page.getByTestId('console-form-save'));
});
