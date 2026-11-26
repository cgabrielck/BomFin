import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('shell remains usable while account request is pending', async ({ page }) => {
  await page.route('**/demo/account.json', () => {});
  const accountRequested = page.waitForRequest('**/demo/account.json');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '值得留意的下一步。' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'AAPL ↗', exact: true })).toBeVisible();
  await expect(page.getByRole('searchbox', { name: '搜尋示範股票' })).toBeEditable();
  await accountRequested;
  await expect(page.getByText('帳戶摘要載入中', { exact: true })).toBeVisible();
});

test('late AAPL response never replaces selected MSFT', async ({ page }) => {
  let started!: () => void, release!: () => void, finished!: () => void;
  const requestStarted = new Promise<void>((resolve) => {
    started = resolve;
  });
  const released = new Promise<void>((resolve) => {
    release = resolve;
  });
  const oldFinished = new Promise<void>((resolve) => {
    finished = resolve;
  });
  await page.route('**/demo/markets/AAPL.json', async (route) => {
    started();
    await released;
    await route.fulfill({ path: 'apps/desk-web/public/demo/markets/AAPL.json' }).catch(() => {});
    finished();
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'AAPL ↗', exact: true }).click();
  await requestStarted;
  await page.getByRole('button', { name: /^MSFT Microsoft/ }).click();
  await expect(page.getByTestId('selected-symbol')).toHaveText('MSFT');
  await expect(page.getByTestId('last-price')).toHaveText('420.00');
  release();
  await oldFinished;
  await page.evaluate(() => new Promise(requestAnimationFrame));
  await expect(page.getByTestId('last-price')).toHaveText('420.00');
  await expect(page.getByTestId('selected-symbol')).toHaveText('MSFT');
});

test('watch is shared between home and detail and resets on reload', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'AAPL 加入自選', exact: true }).click();
  await page.getByRole('button', { name: '我的自選', exact: true }).click();
  await expect(page.locator('.opportunity')).toHaveCount(1);
  await page.getByRole('button', { name: 'AAPL ↗', exact: true }).click();
  await expect(page.getByRole('button', { name: '✓ 已加入自選', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await page.reload();
  await expect(page.getByRole('button', { name: '＋ 加入自選', exact: true })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
});

test('missing and offline scenarios stay explicit and never invent bars', async ({ page }) => {
  await page.goto('/#stock/MSFT');
  await expect(page.getByTestId('last-price')).toHaveText('420.00');
  await page.getByRole('combobox', { name: '示範情境' }).selectOption('offline');
  await expect(page.getByText(/離線情境：保留最後示範資料/)).toBeVisible();
  await page.getByRole('combobox', { name: '示範情境' }).selectOption('missing');
  await expect(page.getByTestId('last-price')).toHaveText('—');
  await expect(page.getByText('尚無可靠 K 線資料', { exact: true })).toBeVisible();
  await expect(page.locator('canvas')).toHaveCount(0);
});

test('foreign-instrument payload fails without showing its price', async ({ page }) => {
  const data = JSON.parse(
    await readFile(
      new URL('../../apps/desk-web/public/demo/markets/AAPL.json', import.meta.url),
      'utf8',
    ),
  );
  data.quotes[0].instrument_id = '22222222-2222-4222-8222-222222222222';
  await page.route('**/demo/markets/AAPL.json', (route) => route.fulfill({ json: data }));
  await page.goto('/#stock/AAPL');
  await expect(page.getByRole('alert')).toContainText('識別不一致');
  await expect(page.getByTestId('last-price')).toHaveText('—');
});

test('mobile navigation and unsupported symbols remain usable', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('navigation', { name: '手機導航' })).toBeVisible();
  await page.getByRole('button', { name: 'NVDA ↗', exact: true }).click();
  await expect(page.getByTestId('last-price')).toHaveText('140.00');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.goto('/#stock/UNKNOWN');
  await expect(page.getByRole('heading', { name: '不在示範股票清單' })).toBeVisible();
  await page.getByRole('button', { name: '返回首頁', exact: true }).click();
  await expect(page.getByRole('heading', { name: '值得留意的下一步。' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('empty candidates keep navigation and reset available', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('combobox', { name: '示範情境' }).selectOption('empty');
  await expect(page.getByText('目前沒有符合的股票', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '重設篩選', exact: true }).click();
  await expect(page.getByRole('button', { name: 'AAPL ↗', exact: true })).toBeVisible();
});
