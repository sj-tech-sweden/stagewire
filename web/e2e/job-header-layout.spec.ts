import { test, expect } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

// The job header (title/venue/date + action buttons) must stay readable at tablet and
// narrow-desktop widths: the title block may not be crushed into a sliver by the buttons.

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

for (const width of [420, 700, 900, 1100]) {
  test(`job header keeps a readable title at ${width}px`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 800 });
    await login(page);
    const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
    const res = await request.post(`${API_BASE}/api/v1/jobs`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { title: `Header ${Date.now()}` },
    });
    const job = await res.json();
    await page.goto(`/jobs/${job.id}/workspace`);
    const summary = page.getByTestId('job-summary');
    await expect(summary).toBeVisible();
    // A crushed title is ~50px wide; the 18rem basis keeps it well above that.
    expect((await summary.boundingBox())!.width).toBeGreaterThan(150);
    // No horizontal page scroll.
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

// Phones: secondary actions live in one menu whose entries carry both an icon and a text label
// (icon-only buttons were unclear and tooltips don't exist on touch).
test('phone header moves secondary actions into a labelled menu', async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  const res = await request.post(`${API_BASE}/api/v1/jobs`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { title: `Header ${Date.now()}` },
  });
  const job = await res.json();
  await page.goto(`/jobs/${job.id}/workspace`);
  await expect(page.getByTestId('open-reports')).toHaveCount(0);
  await page.getByTestId('header-more-menu').click();
  await expect(page.getByTestId('more-open-reports')).toContainText(/PDF/i);
  await expect(page.getByTestId('more-open-share')).toBeVisible();
  await expect(page.getByTestId('more-import')).toBeVisible();
});
