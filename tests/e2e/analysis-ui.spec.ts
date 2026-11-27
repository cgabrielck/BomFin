import { test, expect } from './fixtures/secure-market';
import type { Page } from '@playwright/test';

/**
 * The browser surfaces for the three analysis endpoints.
 *
 * These tests check what a reader actually sees, not what the API
 * returns. The distinction matters: an endpoint can answer correctly
 * and the UI can still mislead, by drawing a value that does not exist
 * or by showing a number without the date that makes it interpretable.
 *
 * The fixtures are routed at the network level so each error shape can
 * be produced on demand. The real endpoints are covered by the backend's
 * own `analysis.spec.ts`; this file is about the browser's honesty.
 */

const ID = '11111111-1111-4111-8111-111111111111';

test.use({ ignoreHTTPSErrors: true, trace: 'off' });

/** The shape of one indicator point, as the contract spells it. */
function point(
  indicator: string,
  value: string,
  minute: number,
): Record<string, unknown> {
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

/** An indicator response with one series and one status. */
function indicatorBody(): Record<string, unknown> {
  return {
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
      {
        schema_version: '1.0',
        instrument_id: ID,
        indicator: 'macd',
        params: { fast: '12', slow: '26', signal: '9' },
        timeframe: { count: 1, unit: 'minute' },
        source_coverage: 'sip',
        points: [point('macd', '0.42', 31)],
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
  };
}

/** A capability response for a delayed feed that cannot back an entry. */
function capabilityBody(): Record<string, unknown> {
  return {
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
  };
}

/** A macro response whose points carry both dates. */
function macroBody(): Record<string, unknown> {
  return {
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
    ],
  };
}

/** Put the desk into server mode with a live session. */
async function paired(page: Page, market: { origin: string; command: (action: string) => Promise<Record<string, unknown>> }) {
  await page.goto(market.origin + '/#stock/AAPL');
  await page.getByRole('combobox', { name: '資料模式' }).selectOption('server');
  const { code } = await market.command('pair');
  await page.getByLabel('配對碼', { exact: true }).fill(String(code));
  await page.getByRole('button', { name: '配對登入', exact: true }).click();
  await expect(page.getByRole('button', { name: '登出', exact: true })).toBeVisible();
}

test('the indicator overlay draws the selected series and states the ones without a value', async ({
  page,
  market,
}) => {
  await page.route('**/v1/indicators**', (route) =>
    route.fulfill({ json: indicatorBody() }),
  );
  await paired(page, market);
  // Nothing is drawn until the reader picks something.
  await expect(page.getByTestId('indicator-legend-sma')).toHaveCount(0);
  await page.getByTestId('indicator-toggle-SMA20').click();
  await expect(page.getByTestId('indicator-legend-sma')).toBeVisible();
  // The value is the backend's own string, not a reformatted number.
  await expect(page.getByTestId('indicator-legend-sma')).toContainText('101.50');
  await page.getByTestId('indicator-toggle-RSI14').click();
  await expect(page.getByTestId('indicator-legend-rsi')).toBeVisible();
  await expect(page.getByTestId('indicator-legend-rsi')).toContainText('56.12');
  await page.getByTestId('indicator-toggle-MACD').click();
  await expect(page.getByTestId('indicator-legend-macd')).toBeVisible();
  // The coverage the values were computed from is shown beside the
  // candle coverage.
  await expect(page.getByTestId('indicator-coverage')).toContainText('sip');
});

test('an indicator without enough history shows the reason instead of a line', async ({
  page,
  market,
}) => {
  await page.route('**/v1/indicators**', (route) =>
    route.fulfill({ json: indicatorBody() }),
  );
  await paired(page, market);
  await page.getByTestId('indicator-toggle-ATR14').click();
  const statuses = page.getByTestId('indicator-statuses');
  await expect(statuses).toContainText('ATR 需 14 根，現有 5 根');
  // A status never becomes a line.
  await expect(page.getByTestId('indicator-legend-atr')).toHaveCount(0);
});

test('a missing series keeps the candles and says there is nothing to compute', async ({
  page,
  market,
}) => {
  await page.route('**/v1/indicators**', (route) =>
    route.fulfill({
      status: 404,
      json: { detail: 'Indicator series not found' },
    }),
  );
  await paired(page, market);
  await expect(page.getByTestId('indicator-missing')).toContainText(
    '此標的尚無可計算的歷史序列',
  );
  // The rest of the workspace keeps working; the overlay does not blank
  // the page and does not substitute another instrument's price.
  await expect(page.getByTestId('last-price')).toHaveText('210.00');
});

test('an unavailable indicator plane does not show the previous value as new', async ({
  page,
  market,
}) => {
  await page.route('**/v1/indicators**', (route) =>
    route.fulfill({
      status: 503,
      json: { detail: 'Indicator plane unavailable' },
    }),
  );
  await paired(page, market);
  await expect(page.getByTestId('indicator-unavailable')).toContainText(
    '指標服務暫時不可用',
  );
  await expect(page.getByTestId('indicator-legend-sma')).toHaveCount(0);
});

test('a refused analysis request does not sign the desk out', async ({
  page,
  market,
}) => {
  await page.route('**/v1/indicators**', (route) =>
    route.fulfill({
      status: 401,
      json: { detail: 'Unauthorized' },
    }),
  );
  await paired(page, market);
  await expect(page.getByTestId('indicator-refused')).toBeVisible();
  // The market view keeps working. A refused analysis request is not a
  // logout, and it must not throw away the quote the reader already had.
  await expect(page.getByTestId('last-price')).toHaveText('210.00');
  await expect(page.getByRole('button', { name: '登出', exact: true })).toBeVisible();
});

test('the macro panel shows the observation date and the release date together', async ({
  page,
  market,
}) => {
  await page.route('**/v1/macro**', (route) =>
    route.fulfill({ json: macroBody() }),
  );
  await paired(page, market);
  const row = page.getByTestId('macro-row-DGS10');
  await expect(row).toBeVisible();
  await expect(row).toContainText('2026-02-20');
  await expect(row.getByRole('cell', { name: '4.15', exact: true })).toBeVisible();
  await expect(row).toContainText('Percent');
});

test('the macro panel sends the as_of date the reader chose', async ({
  page,
  market,
}) => {
  const asked: string[] = [];
  await page.route('**/v1/macro**', (route) => {
    asked.push(route.request().url());
    return route.fulfill({ json: macroBody() });
  });
  await paired(page, market);
  await page.getByLabel('截至日期 as_of').fill('2026-03-01');
  await page.getByRole('button', { name: '套用', exact: true }).click();
  await expect.poll(() => asked.length).toBeGreaterThan(0);
  expect(asked.some((url) => url.includes('as_of=2026-03-01'))).toBe(true);
});

test('a source that cannot back an entry says so in words', async ({
  page,
  market,
}) => {
  await page.route('**/v1/capabilities**', (route) =>
    route.fulfill({ json: capabilityBody() }),
  );
  await paired(page, market);
  // The delayed feed cannot back an entry, and says so.
  const alpaca = page.getByTestId('capability-alpaca');
  await expect(alpaca).toBeVisible();
  await expect(alpaca).toContainText('sip');
  await expect(page.getByTestId('capability-latency-alpaca')).toContainText('延遲 15 分');
  await expect(page.getByTestId('capability-fee-alpaca')).toContainText('免費');
  await expect(page.getByTestId('capability-warning-alpaca')).toContainText(
    '不可作為入場依據',
  );
  // The unavailable reason is shown, not blanked out.
  await expect(page.getByTestId('capability-reason-futu')).toContainText(
    '期權 OPRA 無權限',
  );
  // A source that can back an entry carries no warning.
  await expect(page.getByTestId('capability-warning-futu')).toHaveCount(0);
});

test('the demo desk shows sample states rather than sample numbers', async ({
  page,
}) => {
  await page.goto('/#stock/AAPL');
  await expect(page.getByTestId('indicator-demo')).toBeVisible();
  await expect(page.getByTestId('macro-demo')).toBeVisible();
  await expect(page.getByTestId('capabilities-demo')).toBeVisible();
  // No demo number may appear where a real value would.
  await expect(page.getByTestId('indicator-legend-sma')).toHaveCount(0);
  await expect(page.getByTestId('macro-row-DGS10')).toHaveCount(0);
});

test('a browser cannot reach the analysis endpoints, and the desk says so', async ({
  page,
  market,
}) => {
  // The session guard requires an exact `Origin` header. A same-origin
  // GET does not carry one, and a script may not set it. So the
  // analysis endpoints are out of reach from the browser while they are
  // reachable from a server-side client.
  //
  // This test pins that limitation. When the backend relaxes the
  // requirement, this test fails and says the limitation is gone.
  await paired(page, market);
  const fromBrowser = await page.evaluate(async () => {
    const response = await fetch('/v1/capabilities', {
      credentials: 'same-origin',
      cache: 'no-store',
    });
    return response.status;
  });
  const fromClient = await page.request.get(
    `${market.origin}/v1/capabilities`,
    { headers: { Origin: market.origin } },
  );
  expect(fromClient.status()).toBe(200);
  expect(fromBrowser).toBe(401);
  // The desk reports the refusal without signing the reader out.
  await expect(page.getByTestId('capabilities-refused')).toBeVisible();
  await expect(page.getByTestId('last-price')).toHaveText('210.00');
});
