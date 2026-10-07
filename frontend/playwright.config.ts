import { defineConfig } from '@playwright/test';
if (process.env.CI && !process.env.TEST_DATABASE_URL) throw new Error('CI must configure TEST_DATABASE_URL for real workspace tests');
export default defineConfig({
  testDir: './tests',
  use: { baseURL: 'http://127.0.0.1:5173', browserName: 'chromium',
    launchOptions: { channel: 'chromium' } },
  webServer: [
    ...(process.env.TEST_DATABASE_URL ? [{ command: 'uv run python scripts/browser_test_server.py', cwd: '..', url: 'http://127.0.0.1:5001/api/readiness', reuseExistingServer: false, timeout: 60000 }] : []),
    { command: 'npm run dev', url: 'http://127.0.0.1:5173', reuseExistingServer: false },
  ],
});
