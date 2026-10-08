import { test, expect } from '@playwright/test';
test.skip(!process.env.TEST_DATABASE_URL, 'Requires real disposable PostgreSQL');
// Dedicated server has explicit fake model/FX adapters. Never live integration/quality proof.
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFElEQVR4nGOsmBbAgA0wYRUdtBIAFfMBbilI1DUAAAAASUVORK5CYII=', 'base64');
for (const mobile of [false, true]) test(`explicit fake A1/FX: actual PostgreSQL correction/reopen/privacy ${mobile ? 'mobile' : 'desktop'}`, async ({ page, context }) => {
  if (mobile) await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('http://127.0.0.1:5174');
  await page.getByLabel('Describe your report').fill('London 1–4 October 2026 for a client workshop');
  await page.getByRole('button', { name: 'Propose report', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm and create report' }).click();
  const evidence = page.getByRole('region', { name: 'Workspace evidence' });
  await evidence.getByLabel('Workspace files').setInputFiles({ name: 'synthetic.png', mimeType: 'image/png', buffer: png });
  await evidence.getByRole('button', { name: 'Upload evidence' }).click();
  await expect(evidence.getByText('Validated · retained', { exact: true })).toBeVisible();
  const expenses = page.getByRole('region', { name: 'Expense workspace' });
  await expenses.getByLabel('Selected receipt', { exact: true }).selectOption({ label: 'synthetic.png' });
  await expenses.getByRole('button', { name: 'Prepare selected receipt' }).click();
  await expect(page.getByRole('button', { name: 'Open expense', exact: true })).toBeVisible();
  await expect(expenses.getByLabel('Meal type', { exact: true })).toBeVisible();
  await expect(expenses.getByRole('img', { name: 'Selected original receipt' })).toBeVisible();
  await expect(expenses.getByLabel('VAT (optional)', { exact: true })).toHaveValue('');
  await expenses.getByLabel('Meal type', { exact: true }).selectOption('dinner');
  await expenses.locator('#expense-confirm-facts').check();
  await expenses.getByRole('button', { name: 'Save corrections' }).click();
  await expect(expenses.getByText('Adjusted to policy limit', { exact: false })).toBeVisible();
  await expect(expenses.getByText('£62.00', { exact: true })).toBeVisible();
  await expect(expenses.getByText('£50.00', { exact: true })).toBeVisible();
  await expect(expenses.getByText('£12.00', { exact: true })).toBeVisible();
  await page.reload();
  await expect(expenses.getByRole('button', { name: 'Synthetic Kitchen', exact: false })).toBeVisible();
  await expenses.getByRole('button', { name: 'Synthetic Kitchen', exact: false }).click();
  await expect(expenses.locator('#expense-mealType')).toHaveValue('dinner');
  await expenses.locator('#expense-originalAmount').fill('75.00');
  await expenses.locator('#expense-transactionCurrency').fill('EUR');
  await expenses.locator('#expense-confirm-facts').check();
  await expenses.getByRole('button', { name: 'Save corrections' }).click();
  await expect(expenses.getByText('£60.00', { exact: true })).toBeVisible();
  await expenses.getByRole('button', { name: 'Retry extraction', exact: true }).click();
  await expect(expenses.locator('#expense-originalAmount')).toHaveValue('75.00');
  await expect(expenses.locator('#expense-mealType')).toHaveValue('dinner');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const original = await expenses.getByRole('link', { name: 'Download original receipt' }).getAttribute('href');
  expect(await (await context.request.get('http://127.0.0.1:5174' + original)).body()).toEqual(png);
  await page.getByRole('button', { name: 'Manager', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Manager', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(expenses).toHaveCount(0);
  expect((await context.request.get('http://127.0.0.1:5174' + original)).status()).toBe(403);
});

async function newReport(page: import('@playwright/test').Page) {
  await page.getByLabel('Describe your report').fill('London 1–4 October 2026 for a client workshop');
  await page.getByRole('button', { name: 'Propose report', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm and create report' }).click();
  await expect(page.getByRole('region', { name: 'Workspace evidence' })).toBeVisible();
  return new URL(page.url()).searchParams.get('report')!;
}
async function addReceipt(page: import('@playwright/test').Page, name: string, mimeType: string, buffer: Buffer) {
  const evidence = page.getByRole('region', { name: 'Workspace evidence' });
  await evidence.getByLabel('Workspace files').setInputFiles({ name, mimeType, buffer });
  await evidence.getByRole('button', { name: 'Upload evidence' }).click();
  await expect(evidence.getByText('Validated · retained', { exact: true })).toBeVisible({ timeout: 30000 });
  const expenses = page.getByRole('region', { name: 'Expense workspace' });
  await expenses.getByLabel('Selected receipt', { exact: true }).selectOption({ label: name });
  await expenses.getByRole('button', { name: 'Prepare selected receipt' }).click();
  return expenses;
}

test('real PostgreSQL cross-report original reuse retains notice and opens owning expense', async ({ page, context }) => {
  await page.goto('http://127.0.0.1:5174');
  const first = await newReport(page);
  let expenses = await addReceipt(page, 'synthetic.png', 'image/png', png);
  await expect(expenses.locator('#expense-mealType')).toBeVisible();
  await expenses.locator('#expense-mealType').selectOption('dinner');
  await expenses.locator('#expense-confirm-facts').check();
  await expenses.getByRole('button', { name: 'Save corrections' }).click();
  await expect(expenses.getByText('£62.00', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'New report', exact: true }).click();
  const second = await newReport(page);
  expect(second).not.toBe(first);
  expenses = await addReceipt(page, 'synthetic.png', 'image/png', png);
  await expect(expenses.getByText('No second expense or claim was created.', { exact: false })).toBeVisible();
  await expect(expenses.getByText('No expenses yet.', { exact: false })).toBeVisible();
  const link = expenses.getByRole('link', { name: 'Open existing expense', exact: true });
  await expect(link).toBeVisible();
  const owning = await (await context.request.get(`http://127.0.0.1:5174/api/reports/${first}/expenses`)).json();
  const empty = await (await context.request.get(`http://127.0.0.1:5174/api/reports/${second}/expenses`)).json();
  expect(owning.expenses).toHaveLength(1); expect(empty.expenses).toHaveLength(0);
  await link.click();
  await expect(page).toHaveURL(new RegExp(`report=${first}&expense=${owning.expenses[0].id}`));
  await expect(expenses.locator('#expense-mealType')).toHaveValue('dinner');
  await expect(expenses.getByRole('img', { name: 'Selected original receipt' })).toBeVisible();
  expect(await (await context.request.get('http://127.0.0.1:5174' + owning.expenses[0].originalUrl)).body()).toEqual(png);
});

function syntheticPdf() {
  const stream = 'BT /F1 12 Tf 20 70 Td (SYNTHETIC DINNER RECEIPT) Tj ET';
  const objects = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
  let body = '%PDF-1.7\n'; const offsets = [0];
  objects.forEach((object, index) => { offsets.push(Buffer.byteLength(body)); body += `${index + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = Buffer.byteLength(body); body += `xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(body);
}

test('real API/PG PDF context offers explicit readable fallback and byte-exact original download', async ({ page }) => {
  const { readFile } = await import('node:fs/promises');
  await page.goto('http://127.0.0.1:5174'); await newReport(page);
  const pdf = syntheticPdf(); const expenses = await addReceipt(page, 'synthetic.pdf', 'application/pdf', pdf);
  await expect(expenses.locator('#expense-mealType')).toBeVisible();
  await expect(expenses.getByText('Inline PDF viewing is unavailable here', { exact: false })).toBeVisible();
  await expect(expenses.locator('iframe')).toHaveCount(0);
  const downloadReady = page.waitForEvent('download');
  await expenses.getByRole('link', { name: 'Download original receipt' }).click();
  const download = await downloadReady; const file = await download.path();
  expect(file).not.toBeNull(); expect(await readFile(file!)).toEqual(pdf);
  await expect(expenses.locator('#expense-originalAmount')).toHaveValue('62.00'); // explicit fake A1, not PDF extraction proof
});

test('explicit fake A1: category correction opens Air fields, evidence pauses cabin then authorized reread resolves it', async ({ page }) => {
  await page.goto('http://127.0.0.1:5174'); await newReport(page);
  const expenses = await addReceipt(page, 'synthetic-air-fixture.png', 'image/png', png);
  await expect(expenses.locator('#expense-mealType')).toBeVisible();
  await expenses.locator('#expense-category').selectOption('air');
  await expect(expenses.locator('#expense-mealType')).toHaveCount(0);
  await expenses.locator('#expense-journeyType').selectOption('oneWay');
  await expenses.locator('#expense-origin').fill('LHR');
  await expenses.locator('#expense-destination').fill('CDG');
  await expenses.locator('#expense-departureDate').fill('2026-10-02');
  await expenses.locator('#expense-cabinClass').selectOption('economy');
  await expect(expenses.locator('#expense-returnDate')).toHaveCount(0);
  await expenses.locator('#expense-confirm-facts').check();
  await expenses.getByRole('button', { name: 'Save corrections' }).click();
  await expect(expenses.getByText('A self-declaration cannot establish cabin entitlement.', { exact: false })).toBeVisible();
  await expenses.getByRole('button', { name: 'Retry extraction', exact: true }).click();
  await expect(expenses.getByText('Compliant', { exact: false })).toBeVisible();
  await expect(expenses.locator('#expense-cabinClass')).toHaveValue('economy');
  await expect(page.getByRole('region', { name: 'Policy sources' })).toContainText('AIR-03');
});
