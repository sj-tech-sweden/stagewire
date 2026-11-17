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
  // Wait for the venue to exist and be linked to the form before submitting: the venue is shown in
  // the picker as soon as it is created, but the form only holds its id once the response returns.
  const venueCreated = page.waitForResponse((r) => r.request().method() === 'POST' && /\/venues$/.test(r.url()));
  await dialog.getByRole('button', { name: /create new venue/i }).click();
  await venueCreated;
  await expect(dialog.getByText(venue)).toBeVisible();
  // The venue list stays expanded after creating a venue and covers the Create button. Clicking
  // the dialog heading closes it without dismissing the dialog.
  await dialog.getByText('New production job').click();

  // The dialog also holds an inline "Create new venue …" button; match the job's own "Create"
  // exactly so the inline venue action isn't picked up by the same selector.
  const venueAssigned = page.waitForResponse((r) => r.request().method() === 'PUT' && /\/jobs\/[^/]+\/venue$/.test(r.url()));
  await dialog.getByRole('button', { name: 'Create', exact: true }).click();
  await venueAssigned;

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
  // sv-SE. The switcher saves the language to the shared admin account, so restore English in
  // finally: other specs in the run expect it. We must NOT reload in between: on reload the app
  // re-resolves the locale from the stored preferred_language.
  try {
    // Wait for the save to land: the switcher's PUT is fire-and-forget, so without this the restore
    // below could race it and leave Swedish stored on the shared account.
    const saved = page.waitForResponse(
      (r) => r.request().method() === 'PUT' && /\/auth\/users\//.test(r.url()),
    );
    await page.getByTestId('language-switcher').click();
    await page.getByTestId('lang-sv').click();
    await saved;

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
  } finally {
    const me = await (await request.get(`${API_BASE}/api/v1/auth/me`, { headers })).json();
    await request.put(`${API_BASE}/api/v1/auth/users/${me.id}`, { headers, data: { preferred_language: 'en' } });
  }
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

test('the event date and time are chosen together in one picker popup', async ({ page, request }) => {
  await login(page);
  const token = await page.evaluate(() => localStorage.getItem('sw_access_token'));

  const title = `Combined ${Date.now()}`;
  await page.getByRole('button', { name: /new job/i }).click();
  const dialog = page.locator('.q-dialog');
  await dialog.locator('input').nth(0).fill(title);

  const picker = dialog.locator('.q-input', { hasText: /event date|evenemangsdatum/i });
  await picker.click();

  // The combined picker opens a single popup holding BOTH the calendar (q-date) and the clock
  // (q-time) — not two separate icon popups.
  await expect(page.locator('.q-date')).toBeVisible();
  await expect(page.locator('.q-time')).toBeVisible();

  const today = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  const expectedDate = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;

  // Pick a date (Today) and a time (14:30 via the clock dial). The q-time needs both an hour and a
  // minute before it emits a complete value, so click hour 14 then minute 30. Both update one field.
  await page.locator('.q-date').getByRole('button', { name: 'Today', exact: true }).first().click();
  await expect(picker.locator('input')).toHaveValue(expectedDate);

  await page.locator('.q-time .q-time__clock-pos-14').click();
  // The minute ring is labelled in 5-minute steps; pick "30" by its exact text (the position
  // class collides with the hour ring, so match the label instead).
  await page.locator('.q-time').getByText('30', { exact: true }).click();
  // The field now shows date + 24h time once both parts are chosen.
  await expect(picker.locator('input')).toHaveValue(new RegExp(`^${expectedDate} 14:30$`));

  // Close via the popup's OK button and save.
  await page.getByRole('button', { name: 'OK', exact: true }).click();
  await dialog.getByTestId('job-create').click();
  await dialog.waitFor({ state: 'hidden', timeout: 10000 });

  // The persisted event_date carries the chosen time (date + HH:mm), not just the date.
  await expect
    .poll(
      async () => {
        const listings = await (
          await request.get(`${API_BASE}/api/v1/jobs`, {
            headers: { Authorization: `Bearer ${token}` },
          })
        ).json();
        return listings.find((j) => j.title === title)?.event_date ?? '';
      },
      { timeout: 10000 },
    )
    .toMatch(/14:30/);
});

