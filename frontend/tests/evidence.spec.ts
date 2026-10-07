import { test, expect, type Page } from '@playwright/test';

test.skip(!process.env.TEST_DATABASE_URL, 'Real PostgreSQL/API evidence tests require TEST_DATABASE_URL');
// Standalone synthetic image; no held-out fixture or expected expense facts.
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFElEQVR4nGOsmBbAgA0wYRUdtBIAFfMBbilI1DUAAAAASUVORK5CYII=', 'base64');

async function create(page: Page) {
  await page.getByLabel('Describe your report').fill('London 1–4 October 2026 for a client workshop');
  await page.getByRole('button', { name: 'Propose report', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm and create report' }).click();
  await expect(page.getByRole('region', { name: 'Workspace evidence' })).toBeVisible();
}

test('real chat and workspace upload dedup, worker validation, original download, reload and persona privacy', async ({ page, context }) => {
  await page.goto('/'); await create(page);
  const chat = page.getByRole('region', { name: 'Chat evidence' });
  const workspace = page.getByRole('region', { name: 'Workspace evidence' });
  await chat.getByLabel('Chat files').setInputFiles({ name: 'receipt.png', mimeType: 'image/png', buffer: png });
  await chat.getByRole('button', { name: 'Upload evidence' }).click();
  await expect(chat.getByText('Evidence saved', { exact: false })).toBeVisible();
  await expect(workspace.getByText('Validated · retained', { exact: true })).toBeVisible({ timeout: 30000 });
  await workspace.getByLabel('Workspace files').setInputFiles({ name: 'renamed.png', mimeType: 'image/png', buffer: png });
  await workspace.getByRole('button', { name: 'Upload evidence' }).click();
  await expect(workspace.getByText('1 existing document(s) reused.', { exact: false })).toBeVisible();
  await expect(workspace.getByText('chat / workspace', { exact: false })).toBeVisible();
  await expect(workspace.getByRole('link', { name: 'Download original' })).toHaveCount(1);
  const original = await workspace.getByRole('link', { name: 'Download original' }).getAttribute('href');
  const response = await context.request.get(original!);
  expect(await response.body()).toEqual(png);
  const downloadEvent = page.waitForEvent('download');
  await workspace.getByRole('link', { name: 'Download original' }).click();
  expect((await downloadEvent).suggestedFilename()).toBe('receipt.png');
  await page.screenshot({ path: '../artifacts/local/phase1b-desktop.png', fullPage: true });
  await page.reload();
  await expect(workspace.getByText('Validated · retained', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Manager', exact: true }).click();
  await expect(workspace).toHaveCount(0);
  expect((await context.request.get(original!)).status()).toBe(403);
});

test('mobile invalid evidence fails honestly, correct upload recovers and selecting another report clears evidence', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/'); await create(page);
  const workspace = page.getByRole('region', { name: 'Workspace evidence' });
  await workspace.getByLabel('Workspace files').setInputFiles({ name: 'broken.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.7\nbroken') });
  await workspace.getByRole('button', { name: 'Upload evidence' }).click();
  await expect(workspace.getByRole('alert')).toContainText('File rejected');
  await expect(workspace.getByRole('link', { name: 'Download original' })).toHaveCount(0);
  await workspace.getByLabel('Workspace files').setInputFiles({ name: 'mobile.png', mimeType: 'image/png', buffer: png });
  await workspace.getByRole('button', { name: 'Upload evidence' }).click();
  await expect(workspace.getByText('Validated · retained', { exact: true })).toBeVisible({ timeout: 30000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '../artifacts/local/phase1b-mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'New report', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Chat evidence' })).toHaveCount(0);
  await create(page);
  await expect(workspace.getByText('No evidence yet.', { exact: false })).toBeVisible();
  await expect(workspace.getByRole('link', { name: 'Download original' })).toHaveCount(0);
});
