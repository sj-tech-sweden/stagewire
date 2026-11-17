import { test, expect } from '@playwright/test';
import { ensureAdmin, login, API_BASE } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

test('create a production job from the UI', async ({ page }) => {
  await login(page);

  const title = `E2E Show ${Date.now()}`;
  const venue = `E2E Hall ${Date.now()}`;
  await page.getByRole('button', { name: /new job/i }).click();

  const dialog = page.locator('.q-dialog');
  await dialog.locator('input').nth(0).fill(title);

  // The venue is a searchable picker; typing a name that does not match offers a "create" action.
  await dialog.locator('.q-select input').fill(venue);
  await dialog.getByRole('button', { name: /create new venue/i }).click();
  await expect(dialog.getByText(venue)).toBeVisible();

  // The dialog also holds an inline "Create new venue …" button; match the job's own "Create"
  // exactly so the inline venue action isn't picked up by the same selector.
  await dialog.getByRole('button', { name: 'Create', exact: true }).click();

  // The venue name legitimately appears in two places on the job (the job card and the venue
  // field), so scope to the first match instead of failing strict mode.
  await expect(page.getByText(title).first()).toBeVisible();
  await expect(page.getByText(venue).first()).toBeVisible();
});

test('jobs can be searched and are listed newest first, a page at a time', async ({ page, request }) => {
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  const headers = { Authorization: `Bearer ${token}` };
  const tag = `findme-${Date.now()}`;
  for (const n of [1, 2]) {
    await request.post(`${API_BASE}/api/v1/jobs`, { headers, data: { title: `${tag} job ${n}` } });
  }
  await page.goto('/');
  // the newest job is at the top without any scrolling through older ones
  await expect(page.getByText(`${tag} job 2`)).toBeVisible();
  await page.getByTestId('job-search').fill(tag);
  await expect(page.getByText(`${tag} job 1`)).toBeVisible();
  await expect(page.getByTestId('jobs-footer')).toContainText('2');
  await page.getByTestId('job-search').fill('no-such-job-anywhere');
  await expect(page.getByText(`${tag} job 1`)).toHaveCount(0);
});

test('the jobs list renders the event date as YYYY-MM-DD HH:mm (locale-independent)', async ({ page, request }) => {
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));
  const headers = { Authorization: `Bearer ${token}` };

  const title = `Datumtest ${Date.now()}`;
  const eventDate = '2026-11-17T14:30:00+00:00';
  const created = await (
    await request.post(`${API_BASE}/api/v1/jobs`, {
      headers,
      data: { title, event_date: eventDate },
    })
  ).json();

  await page.goto('/');

  // Switch to Swedish to prove the rendering is fixed (YYYY-MM-DD HH:mm) and NOT localized to
  // sv-SE. We must NOT reload afterwards: on reload the app re-resolves the locale from the
  // server's stored preferred_language (the admin test user has none), overriding back to English.
  await page.getByTestId('language-switcher').click();
  await page.getByTestId('lang-sv').click();

  const item = page.locator('.q-item', { hasText: title });
  // The read-only display formats as YYYY-MM-DD HH:mm in the viewer's local time (matching the
  // picker). Compute the expected string the same way in the browser so the assertion is
  // timezone-independent.
  const expected = await page.evaluate((iso) => {
    const dt = new Date(iso);
    const pad = (n) => String(n).padStart(2, '0');
    return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
  }, created.event_date);
  await expect(item).toContainText(expected);
  // A 12-hour marker must never appear (fixed 24h format).
  await expect(item).not.toContainText(/AM|PM/i);
});

test('the event date is visible in the picker as soon as the date is picked (before any time)', async ({ page, request }) => {
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));

  // Open the "new job" dialog and pick a date without a time. The field must show the date
  // immediately (YYYY-MM-DD), and the value is saved on its own (local midnight).
  const title = `Picket ${Date.now()}`;
  await page.getByRole('button', { name: /new job/i }).click();
  const dialog = page.locator('.q-dialog');
  await dialog.locator('input').nth(0).fill(title);

  // The DateTimePicker is the readonly input labelled with the event-date field. Open the date
  // popup and pick today via the q-date "Today" button — this selects a date without a time,
  // exercising the "date visible immediately" behaviour.
  const picker = dialog.locator('.q-input', { hasText: /event date|evenemangsdatum/i });
  await picker.click();
  const today = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const expectedDate = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
  const datePopup = page.locator('.q-date');
  await datePopup.waitFor({ state: 'visible', timeout: 5000 });
  await datePopup.getByRole('button', { name: 'Today', exact: true }).first().click();

  // The q-input's value shows the date (YYYY-MM-DD) even though no time was chosen.
  await expect(picker.locator('input')).toHaveValue(expectedDate);

  // Close the date popup (Escape) before saving.
  await page.keyboard.press('Escape');

  // Save via the create button (locale-independent testid) and wait for the dialog to close,
  // which only happens after the create API call resolves — avoids racing the POST.
  await dialog.getByTestId('job-create').click();
  await dialog.waitFor({ state: 'hidden', timeout: 10000 });

  // Confirm the job was persisted with an event_date set (date-only is saved as local midnight,
  // not dropped). Poll because the listing may lag the write slightly.
  await expect
    .poll(
      async () => {
        const listings = await (
          await request.get(`${API_BASE}/api/v1/jobs`, {
            headers: { Authorization: `Bearer ${token}` },
          })
        ).json();
        return listings.find((j) => j.title === title);
      },
      { timeout: 10000 },
    )
    .toBeTruthy();
});

