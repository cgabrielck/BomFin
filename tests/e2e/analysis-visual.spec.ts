import { test, expect } from './fixtures/secure-market';

/**
 * A visual check of the three panels.
 *
 * This test exists to leave a picture behind, not to assert. The
 * assertions live in the other files; here the point is that a person
 * can look at the result and see whether the layout holds.
 */
test.use({ ignoreHTTPSErrors: true, trace: 'off' });

const ID = '11111111-1111-4111-8111-111111111111';

function point(indicator: string, value: string, minute: number) {
  return {
    schema_version: '1.0',
    instrument_id: ID,
    indicator,
    params: { period: '20' },
    timeframe: { count: 1, unit: 'minute' },
    value,
    event_at: `2026-11-25T14:${String(minute).padStart(2, '0')}:00Z`,
    computed_at: `2026-11-25T14:${String(minute).padStart(2, '0')}:00Z`,
    source_coverage: 'sip',
    computed_by: 'local',
  };
}

test('the three panels render', async ({ page, market }, testInfo) => {
  await page.route('**/v1/indicators**', (route) =>
    route.fulfill({
      json: {
        schema_version: '1.0',
        instrument_id: ID,
        timeframe: { count: 1, unit: 'minute' },
        source_coverage: 'sip',
        computed_by: 'local',
        series: [
          {
            schema_version: '1.0',
            instrument_id: ID,
            indicator: 'sma',
            params: { period: '20' },
            timeframe: { count: 1, unit: 'minute' },
            source_coverage: 'sip',
            points: [point('sma', '101.25', 30), point('sma', '101.50', 31)],
          },
          {
            schema_version: '1.0',
            instrument_id: ID,
            indicator: 'rsi',
            params: { period: '14' },
            timeframe: { count: 1, unit: 'minute' },
            source_coverage: 'sip',
            points: [point('rsi', '56.12', 31)],
          },
        ],
        statuses: [
          {
            indicator: 'atr',
            params: { period: '14' },
            ready: false,
            reason: 'insufficient_history',
            required_bars: 14,
            observed_bars: 5,
          },
        ],
      },
    }),
  );
  await page.route('**/v1/macro**', (route) =>
    route.fulfill({
      json: {
        schema_version: '1.0',
        observed_at: '2026-11-27T00:00:00Z',
        as_of: '2026-03-01',
        points: [
          {
            schema_version: '1.0',
            series_id: 'DGS10',
            observation_date: '2026-02-20',
            release_date: '2026-02-20',
            value: '4.15',
            units: 'Percent',
            frequency: 'daily',
            vintage: null,
          },
          {
            schema_version: '1.0',
            series_id: 'T10Y2Y',
            observation_date: '2026-02-19',
            release_date: '2026-02-20',
            value: '-0.38',
            units: 'Percent',
            frequency: 'daily',
            vintage: null,
          },
        ],
      },
    }),
  );
  await page.route('**/v1/capabilities**', (route) =>
    route.fulfill({
      json: {
        schema_version: '1.0',
        checked_at: '2026-11-27T00:00:00Z',
        sources: [
          {
            schema_version: '1.0',
            source: 'alpaca',
            asset_classes: ['equity'],
            sessions: ['regular'],
            latency_label: 'delayed',
            max_subscriptions: null,
            history_limits: [],
            checked_at: '2026-11-27T00:00:00Z',
            permission_errors: [],
            sequence_rules: [],
            venue_coverage: 'sip',
            realtime: false,
            delay_minutes: 15,
            tradable_for_entry: false,
            depth_levels: null,
            fee_class: 'none',
            unavailable_reason: null,
          },
          {
            schema_version: '1.0',
            source: 'futu',
            asset_classes: ['equity'],
            sessions: ['regular'],
            latency_label: 'realtime',
            max_subscriptions: null,
            history_limits: [],
            checked_at: '2026-11-27T00:00:00Z',
            permission_errors: [],
            sequence_rules: [],
            venue_coverage: 'futu_nasdaq_totalview',
            realtime: true,
            delay_minutes: null,
            tradable_for_entry: true,
            depth_levels: 10,
            fee_class: 'exchange',
            unavailable_reason: '期權 OPRA 無權限',
          },
        ],
      },
    }),
  );
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(market.origin + '/#stock/AAPL');
  await page.getByRole('combobox', { name: '資料模式' }).selectOption('server');
  const { code } = await market.command('pair');
  await page.getByLabel('配對碼', { exact: true }).fill(String(code));
  await page.getByRole('button', { name: '配對登入', exact: true }).click();
  await expect(page.getByRole('button', { name: '登出', exact: true })).toBeVisible();
  await page.getByTestId('indicator-toggle-SMA20').click();
  await page.getByTestId('indicator-toggle-RSI14').click();
  await expect(page.getByTestId('indicator-legend-rsi')).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath('analysis-panels.png'),
    fullPage: true,
  });
});
