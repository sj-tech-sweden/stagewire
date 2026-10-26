import { test, expect } from '@playwright/test';
import { ensureAdmin, login } from './helpers';

test.beforeEach(async ({ request }) => {
  await ensureAdmin(request);
});

test('admin can open the WYSIWYG report editor with registered data fields', async ({ page }) => {
  await login(page);
  await page.goto('/reports');

  await expect(page.getByRole('main').getByText('Report templates', { exact: true })).toBeVisible();
  await page.getByRole('combobox', { name: 'Template', exact: true }).click();
  await page.getByText('Stage plot · Default', { exact: true }).click();
  await expect(page.locator('.q-editor')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Job title' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stage elements' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stage plot diagram' })).toBeVisible();
  await expect(page.locator('.report-layout-object')).toHaveCount(2);
  await expect(page.getByRole('combobox', { name: 'Plot area' })).toBeVisible();
  await expect(page.getByText('Speaker coverage', { exact: true })).toBeVisible();
  await expect(page.getByText('Cables', { exact: true })).toBeVisible();
  await expect(page.getByText('Cableways', { exact: true })).toBeVisible();
  const stagePlotHeight = await page
    .locator('.report-layout-object')
    .nth(1)
    .evaluate((element) => Number.parseFloat(element.style.height));
  expect(stagePlotHeight).toBeGreaterThan(80);

  await page.getByRole('tab', { name: 'Page 2' }).click();
  await expect(page.locator('.report-layout-object')).toHaveCount(1);
  await page.getByRole('tab', { name: 'Page 1' }).click();

  const dragHandle = page.locator('.report-layout-object__handle').first();
  const initialLeft = await page.locator('.report-layout-object').first().evaluate((item) => item.style.left);
  const handleBounds = await dragHandle.boundingBox();
  if (!handleBounds) throw new Error('Report object handle is not visible');
  await page.mouse.move(handleBounds.x + 24, handleBounds.y + 9);
  await page.mouse.down();
  await page.mouse.move(handleBounds.x + 74, handleBounds.y + 29, { steps: 5 });
  await page.mouse.up();
  await expect
    .poll(() => page.locator('.report-layout-object').first().evaluate((item) => item.style.left))
    .not.toBe(initialLeft);

  await page.getByRole('combobox', { name: 'Template language' }).click();
  await page.getByText('Swedish', { exact: true }).click();
  await expect(page.getByLabel('Template name')).toHaveValue('Scenritning');

  await page.setViewportSize({ width: 375, height: 812 });
  const mobileLayout = await page.evaluate(() => {
    const editor = document.querySelector('.q-editor__content');
    const heading = editor?.querySelector('h1');

    return {
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      editorWidth: editor?.clientWidth ?? 0,
      editorScrollWidth: editor?.scrollWidth ?? 0,
      headingFontSize: heading ? Number.parseFloat(getComputedStyle(heading).fontSize) : 0,
    };
  });

  expect(mobileLayout.documentWidth).toBeLessThanOrEqual(mobileLayout.viewportWidth);
  expect(mobileLayout.editorScrollWidth).toBeLessThanOrEqual(mobileLayout.editorWidth);
  expect(mobileLayout.headingFontSize).toBeLessThanOrEqual(24);
});

test('report editor includes the selected patchpoint in the PDF preview request', async ({ page }) => {
  const jobId = 'f5a1cbe0-60e1-4262-9d92-c64c6c057767';
  const firstDeviceId = '132164e4-f313-4fd1-bb7c-e181e44bdc47';
  const selectedDeviceId = '232164e4-f313-4fd1-bb7c-e181e44bdc47';
  const templateId = '332164e4-f313-4fd1-bb7c-e181e44bdc47';
  let previewRequestUrl = '';

  await login(page);
  await page.route('**/api/v1/reports/types**', (route) =>
    route.fulfill({
      json: [
        {
          key: 'audio.patch-sheet',
          domain: 'audio',
          report_type: 'patch-sheet',
          name: 'Patch sheet',
          description: 'Patchpoint details',
          fields: [],
          tables: [],
          requires_patchpoint: true,
        },
      ],
    }),
  );
  await page.route('**/api/v1/reports/templates**', (route) =>
    route.fulfill({
      json: [
        {
          id: templateId,
          domain: 'audio',
          report_type: 'patch-sheet',
          locale: 'en',
          name: 'Patch sheet',
          description: 'Patchpoint details',
          body_html: '<h1>{{patchpoint.name}}</h1>',
          layout_json: null,
          page_count: 1,
          stage_plot_options: null,
          is_default: true,
          is_builtin: true,
          letterhead_id: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
    }),
  );
  await page.route('**/api/v1/reports/letterheads', (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route('**/api/v1/jobs', (route) =>
    route.fulfill({
      json: [
        {
          id: jobId,
          title: 'Preview job',
          venue_name: 'Preview venue',
          cable_plan: {},
        },
      ],
    }),
  );
  await page.route(`**/api/v1/jobs/${jobId}/plot-elements`, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route(`**/api/v1/jobs/${jobId}/channel-lists`, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route(`**/api/v1/jobs/${jobId}/devices`, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route(`**/api/v1/jobs/${jobId}/patch-sheets`, (route) =>
    route.fulfill({
      json: [
        { device_id: firstDeviceId, name: 'Stagebox A', point_type: 'stagebox', channels: [] },
        { device_id: selectedDeviceId, name: 'Stagebox B', point_type: 'stagebox', channels: [] },
      ],
    }),
  );
  await page.route('**/api/v1/reports/jobs/*/audio/patch-sheet/preview**', async (route) => {
    previewRequestUrl = route.request().url();
    await route.fulfill({
      status: 200,
      contentType: 'application/pdf',
      body: '%PDF-1.4',
    });
  });

  await page.goto('/reports');
  const patchpointSelect = page.getByRole('combobox', { name: 'Patchpoint' });
  await expect(patchpointSelect).toBeVisible();
  await patchpointSelect.click();
  await page.getByText('Stagebox B', { exact: true }).click();
  await page.getByRole('button', { name: 'Preview PDF' }).click();

  await expect.poll(() => previewRequestUrl).not.toBe('');
  expect(new URL(previewRequestUrl).searchParams.get('patchpoint_id')).toBe(selectedDeviceId);
  expect(new URL(previewRequestUrl).searchParams.get('template_id')).toBe(templateId);
});

test('letterhead printable-area preview updates before margins are saved', async ({ page }) => {
  await login(page);
  await page.route('**/reports/letterheads', async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([
        {
          id: 'd48a28a0-209d-4c99-98b1-c093e286b209',
          name: 'Preview letterhead',
          page_width_pt: 595.28,
          page_height_pt: 841.89,
          margin_top_mm: 20,
          margin_bottom_mm: 20,
          margin_left_mm: 20,
          margin_right_mm: 20,
          is_default: true,
          created_at: new Date().toISOString(),
        },
      ]),
    });
  });
  await page.route('**/reports/letterheads/*/preview', async (route) => {
    await route.fulfill({
      contentType: 'image/png',
      body: Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/S4cAAAAASUVORK5CYII=',
        'base64',
      ),
    });
  });
  await page.goto('/reports');
  await page.getByText('Preview letterhead', { exact: true }).click();
  const printableArea = page.locator('.letterhead-printable');
  const initialTop = await printableArea.evaluate((element) => element.style.top);
  await page.getByRole('spinbutton', { name: 'Top mm' }).fill('30');
  await expect
    .poll(() => printableArea.evaluate((element) => element.style.top))
    .not.toBe(initialTop);
});
