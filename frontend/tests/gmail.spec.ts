import { test, expect } from '@playwright/test';

test('unconfigured Gmail is honest, manual intake stays independent and manager hides it', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Describe your report').fill('London 1–4 October 2026 for a client workshop');
  await page.getByRole('button', { name: 'Propose report', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm and create report' }).click();
  const gmail = page.getByRole('region', { name: 'Gmail evidence' });
  await expect(gmail).toContainText('Gmail is not configured');
  await expect(gmail).toContainText('No send, modify or continuous monitoring');
  await expect(page.getByRole('button', { name: 'Connect Gmail', exact: true })).toHaveCount(0);
  await page.reload();
  await expect(gmail).toContainText('Gmail is not configured');
  await page.getByRole('button', { name: 'Manager', exact: true }).click();
  await expect(gmail).toHaveCount(0);
});
