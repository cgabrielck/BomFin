import { test, expect } from './fixtures/secure-market';
import type { Bar } from '../../apps/desk-web/src/shared/contracts/generated';
import { BarSeries } from '../../apps/desk-web/src/features/chart/bar-series';

const ID = '11111111-1111-4111-8111-111111111111';
const scope = {
  instrumentId: ID,
  source: 'fixture',
  timeframe: { count: 1, unit: 'minute' as const },
};
test.use({ barsEnabled: true, ignoreHTTPSErrors: true, trace: 'off' });
function bar(minute: number, changes: Partial<Bar> = {}): Bar {
  return {
    schema_version: '1.0',
    instrument_id: ID,
    source: 'fixture',
    timeframe: scope.timeframe,
    session: 'regular',
    start: `2026-11-25T14:${minute}:00Z`,
    end: `2026-11-25T14:${minute + 1}:00Z`,
    open: '100',
    high: '105',
    low: '99',
    close: '103',
    volume: '100',
    status: 'forming',
    revision: 0,
    corporate_action_policy: 'unadjusted-fixture',
    event_at: '2026-11-25T14:35:00Z',
    received_at: '2026-11-25T14:35:00Z',
    available_at: '2026-11-25T14:35:00Z',
    ...changes,
  };
}

test('forming candle replaces its interval and volume without resetting history', () => {
  const series = new BarSeries(scope);
  expect(series.applyBars([bar(30), bar(31)]).reset).toBe(true);
  const patch = series.applyBars([
    bar(30),
    bar(31, { close: '104', volume: '150' }),
  ]);
  expect(patch.reset).toBe(false);
  expect(patch.changes).toEqual([
    { bar: bar(31, { close: '104', volume: '150' }), historical: false },
  ]);
  expect(patch.bars.map((value) => value.volume)).toEqual(['100', '150']);
});

test('late revisions change only their interval and stale or regressive bars are ignored', () => {
  const series = new BarSeries(scope);
  const final = bar(30, { status: 'final' }),
    latest = bar(31);
  series.applyBars([final, latest]);
  const corrected = bar(30, {
    status: 'corrected',
    revision: 1,
    close: '104',
    volume: '125',
  });
  const patch = series.applyBars([corrected, latest]);
  expect(patch.reset).toBe(false);
  expect(patch.changes).toEqual([{ bar: corrected, historical: true }]);
  expect(series.applyBars([corrected, latest]).changes).toEqual([]);
  expect(series.applyBars([final, latest]).changes).toEqual([]);
  expect(series.applyBars([bar(30, { revision: 2 }), latest]).changes).toEqual(
    [],
  );
  expect(
    series.applyBars([
      bar(30, {
        ...corrected,
        revision: 2,
        event_at: '2026-11-25T14:34:00Z',
        received_at: '2026-11-25T14:34:00Z',
        available_at: '2026-11-25T14:34:00Z',
      }),
      latest,
    ]).changes,
  ).toEqual([]);
  expect(
    series.applyBars([corrected, latest]).bars.map((value) => value.volume),
  ).toEqual(['125', '100']);
});

test('demo chart draws sourced candles, supports zoom, and leaves missing bars empty', async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/#stock/AAPL');
  await expect(page.getByRole('region', { name: 'K 線圖' })).toBeVisible();
  await expect(page.getByTestId('chart-count')).toHaveText('30');
  await expect(
    page.getByRole('region', { name: 'K 線圖' }).locator('canvas').first(),
  ).toBeVisible();
  const canvas = page
    .getByRole('region', { name: 'K 線圖' })
    .locator('canvas')
    .first();
  const before = await canvas.evaluate((node: HTMLCanvasElement) =>
    node.toDataURL(),
  );
  await page.getByRole('button', { name: '放大圖表', exact: true }).click();
  await expect
    .poll(() =>
      canvas
        .evaluate((node: HTMLCanvasElement) => node.toDataURL())
        .then((value) => value !== before),
    )
    .toBe(true);
  await page.getByRole('button', { name: '重設圖表', exact: true }).click();
  await page.screenshot({
    path: testInfo.outputPath('chart-desktop.png'),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () => (await canvas.boundingBox())!.width)
    .toBeLessThan(390);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
  await page.screenshot({
    path: testInfo.outputPath('chart-desktop.png'),
    fullPage: true,
  });
  expect(errors).toEqual([]);
  await page.getByRole('button', { name: /^NVDA NVIDIA/ }).click();
  await expect(
    page.getByText('尚無可靠 K 線資料', { exact: true }),
  ).toBeVisible();
  await expect(page.locator('canvas')).toHaveCount(0);
  await expect(page.getByTestId('last-price')).toHaveText('140.00');
});

test('identical newer receipts preserve time ordering without drawing again', () => {
  const series = new BarSeries(scope);
  series.applyBars([bar(30)]);
  expect(
    series.applyBars([
      bar(30, {
        received_at: '2026-11-25T14:36:00Z',
        available_at: '2026-11-25T14:36:00Z',
      }),
    ]).changes,
  ).toEqual([]);
  expect(
    series.applyBars([
      bar(30, {
        close: '104',
        received_at: '2026-11-25T14:35:30Z',
        available_at: '2026-11-25T14:35:30Z',
      }),
    ]).changes,
  ).toEqual([]);
});

test('late candle request cannot replace a newer selected instrument', async ({
  page,
}) => {
  let started!: () => void, release!: () => void, finished!: () => void;
  const requested = new Promise<void>((resolve) => (started = resolve)),
    held = new Promise<void>((resolve) => (release = resolve)),
    completed = new Promise<void>((resolve) => (finished = resolve));
  await page.route('**/demo/bars/AAPL.json', async (route) => {
    started();
    await held;
    await route.continue().catch(() => {});
    finished();
  });
  try {
    await page.goto('/#stock/AAPL');
    await requested;
    await page.getByRole('button', { name: /^MSFT Microsoft/ }).click();
    await expect(page.getByTestId('chart-last-close')).toHaveText('419.90');
    release();
    await completed;
    await expect(page.getByTestId('selected-symbol')).toHaveText('MSFT');
    await expect(page.getByTestId('chart-last-close')).toHaveText('419.90');
  } finally {
    release();
  }
});

test('unsafe scope, prices or conflicting finalized revisions never reach drawing', () => {
  for (const changed of [
    { instrument_id: '22222222-2222-4222-8222-222222222222' },
    { source: 'other' },
    { timeframe: { count: 5, unit: 'minute' as const } },
    { close: '999' },
    { high: '1e999' },
    { volume: '-1' },
    { corporate_action_policy: 'adjusted' },
  ]) {
    const series = new BarSeries(scope);
    series.applyBars([bar(30, { status: 'final' })]);
    expect(() => series.applyBars([bar(31, changed)])).toThrow();
  }
  const series = new BarSeries(scope);
  series.applyBars([bar(30, { status: 'final' })]);
  expect(() =>
    series.applyBars([bar(30, { status: 'final', close: '104' })]),
  ).toThrow();
});

test('new historical intervals and bounded retention use explicit resets, empty input clears', () => {
  const series = new BarSeries(scope, 2);
  series.applyBars([bar(31), bar(32)]);
  expect(series.applyBars([bar(30), bar(31), bar(32)]).reset).toBe(true);
  series.applyBars([bar(33)]);
  const compact = series.applyBars([bar(34)]);
  expect(compact.reset).toBe(true);
  expect(compact.bars.map((value) => value.start)).toEqual([
    bar(33).start,
    bar(34).start,
  ]);
  expect(series.applyBars([]).bars).toEqual([]);
  expect(series.applyBars([bar(31)]).reset).toBe(true);
});

test('TLS bar stream replaces forming candles, revises history, and never adds duplicate volume', async ({
  page,
  market,
}) => {
  await page.goto(market.origin + '/#stock/AAPL');
  await page.getByRole('combobox', { name: '資料模式' }).selectOption('server');
  await expect(
    page.getByRole('heading', { name: '登入行情工作台' }),
  ).toBeVisible();
  const { code } = await market.command('pair');
  await page.getByLabel('配對碼', { exact: true }).fill(String(code));
  await page.getByRole('button', { name: '配對登入', exact: true }).click();
  await expect(page.getByTestId('chart-count')).toHaveText('3');
  await market.command('bar', { close: '104', volume: '150' });
  await expect(page.getByTestId('chart-last-close')).toHaveText('104');
  await expect(page.getByTestId('chart-last-volume')).toHaveText('150');
  await market.command('bar', {
    index: 0,
    close: '102',
    volume: '125',
    status: 'corrected',
    revision: 1,
  });
  await page.getByText('檢視 K 線數值（最近 10 根）', { exact: true }).click();
  await expect(
    page.getByRole('cell', { name: '125', exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId('chart-last-close')).toHaveText('104');
  await market.command('repeat_bar');
  await market.command('heartbeat');
  await expect(page.getByTestId('chart-count')).toHaveText('3');
  await expect(page.getByTestId('chart-last-volume')).toHaveText('150');
  await market.command('bar', { close: '104', volume: null });
  await expect(page.getByTestId('chart-last-volume')).toHaveText('—');
  await market.command('bar', { close: '104.5', volume: '175' });
  await expect(page.getByTestId('chart-last-volume')).toHaveText('175');
  await expect(page.getByTestId('last-price')).toHaveText('210.00');
});

test('a reconnect snapshot fully replaces the old chart, including removed intervals', async ({
  page,
  market,
}) => {
  await page.goto(market.origin + '/#stock/AAPL');
  await page.getByRole('combobox', { name: '資料模式' }).selectOption('server');
  await expect(
    page.getByRole('heading', { name: '登入行情工作台' }),
  ).toBeVisible();
  const { code } = await market.command('pair');
  await page.getByLabel('配對碼', { exact: true }).fill(String(code));
  await page.getByRole('button', { name: '配對登入', exact: true }).click();
  await expect(page.getByTestId('chart-count')).toHaveText('3');
  await market.command('bar', {
    close: '108',
    volume: '500',
    status: 'final',
    revision: 1,
  });
  await expect(page.getByTestId('chart-last-close')).toHaveText('108');
  await market.command('reset_bars', { count: 1 });
  await expect(page.getByTestId('chart-count')).toHaveText('1');
  await expect(page.getByTestId('chart-last-close')).toHaveText('103');
  await expect(page.getByTestId('chart-last-volume')).toHaveText('100');
});

test('leaving the chart releases browser subscriptions and removes canvas', async ({
  page,
  market,
}) => {
  let opened = 0,
    closed = 0;
  page.on('websocket', (socket) => {
    opened++;
    socket.on('close', () => closed++);
  });
  await page.goto(market.origin + '/#stock/AAPL');
  await page.getByRole('combobox', { name: '資料模式' }).selectOption('server');
  await expect(
    page.getByRole('heading', { name: '登入行情工作台' }),
  ).toBeVisible();
  const { code } = await market.command('pair');
  await page.getByLabel('配對碼', { exact: true }).fill(String(code));
  await page.getByRole('button', { name: '配對登入', exact: true }).click();
  await expect(page.getByTestId('chart-count')).toHaveText('3');
  await expect.poll(() => opened).toBe(2);
  await page.getByRole('button', { name: '回首頁', exact: true }).click();
  await expect(page.locator('canvas')).toHaveCount(0);
  await expect.poll(() => closed).toBe(opened);
});
