import { test, expect, type Page } from '@playwright/test';

test.skip(!process.env.TEST_DATABASE_URL, 'TEST_DATABASE_URL is required for real PostgreSQL/API workspace tests');
const description = 'Prepare my London expense report for 1–4 October 2026 for a client workshop.';

async function propose(page: Page, message = description) {
  await page.getByLabel('Describe your report').fill(message);
  await page.getByRole('button', { name: 'Propose report', exact: true }).click();
  await expect(page.getByRole('form', { name: 'Review report header' })).toBeVisible();
}

test('real report proposal, correction, confirmation, reload and manager privacy', async ({ page, context }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Employee', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('Grade C · fixed demo profile')).toBeVisible();
  await propose(page);
  await expect(page.getByLabel('Report name', { exact: true })).toHaveValue('London expense report');
  await expect(page.getByLabel('Start date')).toHaveValue('2026-10-01');
  await expect(page.getByLabel('End date')).toHaveValue('2026-10-04');
  await expect(page.getByLabel('Business purpose', { exact: true })).toHaveValue('a client workshop');
  await expect(page.getByRole('complementary', { name: 'Your reports' }).getByText('No saved reports yet.', { exact: false })).toBeVisible();
  await expect(page.getByLabel(/manager email/i)).toHaveCount(0);
  await page.getByLabel('Report name', { exact: true }).fill('Reviewed London workshop');
  await page.getByRole('button', { name: 'Confirm and create report' }).click();
  const report = page.getByRole('region', { name: 'Selected report' });
  await expect(report.getByRole('heading', { name: 'Reviewed London workshop' })).toBeVisible();
  const reportId = new URL(page.url()).searchParams.get('report');
  await page.reload();
  await expect(report.getByRole('heading', { name: 'Reviewed London workshop' })).toBeVisible();
  await page.getByRole('button', { name: 'Manager', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'No submitted reports' })).toBeVisible();
  await expect(page.getByText('Reviewed London workshop')).toHaveCount(0);
  const direct = await context.request.get(`/api/reports/${reportId}`, { headers: { 'X-Persona': 'employee' } });
  expect(direct.status()).toBe(403);
  await page.reload();
  await expect(page.getByRole('button', { name: 'Manager', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Employee', exact: true }).click();
  await expect(report.getByRole('heading', { name: 'Reviewed London workshop' })).toBeVisible();
  await page.screenshot({ path: '../artifacts/local/phase1a-desktop.png', fullPage: true });
});

test('missing year and purpose are reviewed on narrow screens before saving', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await propose(page, 'Prepare my London expense report for 1–4 October');
  await expect(page.getByText('Confirm both dates, including the year', { exact: false })).toBeVisible();
  const before = await context.request.get('/api/reports');
  expect((await before.json()).reports).toEqual([]);
  await page.getByLabel('Report name', { exact: true }).fill('London client visit');
  await page.getByLabel('Start date').fill('2026-10-01');
  await page.getByLabel('End date').fill('2026-10-04');
  await page.getByLabel('Business purpose', { exact: true }).fill('Client workshop');
  await page.getByRole('button', { name: 'Confirm and create report' }).click();
  await expect(page.getByRole('region', { name: 'Selected report' }).getByRole('heading', { name: 'London client visit' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '../artifacts/local/phase1a-mobile.png', fullPage: true });
});

test('a second browser context cannot retrieve the saved draft', async ({ page, browser }) => {
  await page.goto('/'); await propose(page);
  await page.getByRole('button', { name: 'Confirm and create report' }).click();
  await expect(page.getByRole('region', { name: 'Selected report' }).getByRole('heading', { name: 'London expense report' })).toBeVisible();
  const id = new URL(page.url()).searchParams.get('report');
  const other = await browser.newContext();
  const otherPage = await other.newPage();
  try {
    await otherPage.goto('/');
    await expect(otherPage.getByRole('button', { name: 'Employee', exact: true })).toHaveAttribute('aria-pressed', 'true');
    expect((await other.request.get(`/api/reports/${id}`)).status()).toBe(404);
    expect((await (await other.request.get('/api/reports')).json()).reports).toEqual([]);
  } finally { await other.close(); }
});

test('an invalid session requires an explicit fresh start and cannot recover old drafts', async ({ page, context }) => {
  await page.goto('/'); await propose(page);
  await page.getByRole('button', { name: 'Confirm and create report' }).click();
  await expect(page.getByRole('region', { name: 'Selected report' }).getByRole('heading', { name: 'London expense report' })).toBeVisible();
  await context.addCookies([{ name: 'unloop_demo', value: 'forged', url: 'http://127.0.0.1:5173' }]);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Start a new demo session' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'London expense report' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Start new demo session' }).click();
  await expect(page.getByRole('button', { name: 'Employee', exact: true })).toHaveAttribute('aria-pressed', 'true');
  expect((await (await context.request.get('/api/reports')).json()).reports).toEqual([]);
});

test('stale employee UI cannot create a report after the server switches to manager', async ({ page, context }) => {
  await page.goto('/'); await propose(page);
  const session = await (await context.request.get('/api/session')).json();
  const changed = await context.request.patch('/api/session/persona', {
    data: { persona: 'manager' }, headers: { Origin: 'http://127.0.0.1:5173', 'X-CSRF-Token': session.csrfToken },
  });
  expect(changed.status()).toBe(200);
  await page.getByRole('button', { name: 'Confirm and create report' }).click();
  await expect(page.getByRole('heading', { name: 'No submitted reports' })).toBeVisible();
  await expect(page.getByRole('form', { name: 'Review report header' })).toHaveCount(0);
  expect((await (await context.request.get('/api/reports')).json()).reports).toEqual([]);
});

test('lost session cookie after prior use never silently creates a replacement session', async ({ page, context }) => {
  await page.goto('/'); await propose(page);
  await page.getByRole('button', { name: 'Confirm and create report' }).click();
  await expect(page.getByRole('region', { name: 'Selected report' }).getByRole('heading', { name: 'London expense report' })).toBeVisible();
  await context.clearCookies();
  let starts = 0; page.on('request', request => { if (request.url().endsWith('/api/session') && request.method() === 'POST') starts += 1; });
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Start a new demo session' })).toBeVisible();
  expect(starts).toBe(0);
  await page.getByRole('button', { name: 'Start new demo session' }).click();
  await expect(page.getByRole('button', { name: 'Employee', exact: true })).toHaveAttribute('aria-pressed', 'true');
  expect(starts).toBe(1);
});
