import { test, expect } from '@playwright/test';

test('preview distinguishes receipt and claim without pretending to save', async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { service: 'unloop', status: 'ok' } }));
  await page.goto('/?preview=1');
  await expect(page.getByText('Synthetic examples only.')).toBeVisible();
  await expect(page.locator('.claim strong')).toHaveText('£50.00');
  await expect(page.locator('.amounts > div').first().locator('strong')).toHaveText('£62.00');
  await expect(page.getByRole('button', { name: 'Save expense · next phase' })).toBeDisabled();
  await page.screenshot({ path: '../artifacts/local/phase0-desktop.png', fullPage: true });
  await page.getByRole('button', { name: /Unclear meal Market Cafe/ }).click();
  await expect(page.locator('.claim strong')).toHaveText('—');
  await expect(page.getByText('Was this Breakfast, Lunch or Dinner?', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Hide receipt' }).click();
  await expect(page.locator('.receipt')).toHaveCount(0);
  await page.getByRole('button', { name: 'Show receipt' }).click();
  await expect(page.locator('.receipt')).toBeVisible();
});

test('narrow viewport has no horizontal overflow and reports unavailable API', async ({ page }) => {
  await page.route('**/api/health', route => route.abort());
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?preview=1');
  await expect(page.getByText('Local API offline — start the API on port 5001')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '../artifacts/local/phase0-mobile.png', fullPage: true });
});
