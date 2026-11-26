import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: ['market.spec.ts', 'secure-market.spec.ts'],
  timeout: 15000,
  expect: { timeout: 4000 },
  workers: 1,
  fullyParallel: false,
  outputDir: './test-results',
  reporter: [['list'], ['json', { outputFile: 'test-results/results.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:19045',
    channel: 'msedge',
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm.cmd --prefix apps/desk-web run dev -- --port 19045',
    url: 'http://127.0.0.1:19045',
    reuseExistingServer: false,
    timeout: 30000,
  },
});
