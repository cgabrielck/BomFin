import { defineConfig } from '@playwright/test';

/**
 * The research acceptance run, on its own.
 *
 * The shared `playwright.config.ts` starts a vite dev server on port
 * 19045 and points every test at it. The research acceptance run does
 * not need that server at all: it drives a real TLS server that serves
 * the built `dist/` on a port the operating system picked, so the
 * browser talks to the fixture and never to the dev server.
 *
 * This config exists so the research run can start without claiming
 * port 19045. That port belongs to the desk, and two runs fighting over
 * it is a self-inflicted conflict, not a real failure.
 */
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: ['research-flow.spec.ts'],
  timeout: 15000,
  expect: { timeout: 4000 },
  workers: 1,
  fullyParallel: false,
  outputDir: './test-results',
  reporter: [['list']],
  use: {
    channel: 'msedge',
    headless: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
