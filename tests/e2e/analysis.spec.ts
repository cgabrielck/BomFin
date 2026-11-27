import { test, expect } from './fixtures/secure-market';
import type { Page } from '@playwright/test';

/**
 * The analysis surfaces over the real private-TLS fixture.
 *
 * These tests are the backend contract the browser work builds on. They
 * pin the honest parts: a delayed feed must not claim it can back an
 * entry, a macro point must carry the release date it was published on,
 * and an indicator must name the venue it was computed from.
 */

const ID = '11111111-1111-4111-8111-111111111111';

async function paired(
  page: Page,
  market: {
    origin: string;
    command: (action: string) => Promise<Record<string, unknown>>;
  },
) {
  await page.goto(market.origin);
  await page.getByRole('combobox', { name: '資料模式' }).selectOption('server');
  const { code } = await market.command('pair');
  await page.getByLabel('配對碼', { exact: true }).fill(String(code));
  await page.getByRole('button', { name: '配對登入', exact: true }).click();
  await expect(page.getByRole('button', { name: '登出', exact: true })).toBeVisible();
}

// The session authority requires the exact origin, so an API call made
// outside a browser navigation must state it.
function api(market: { origin: string }, path: string) {
  return {
    headers: { Origin: market.origin },
  };
}

test.use({ ignoreHTTPSErrors: true, trace: 'off' });

test('the capability endpoint reports what each feed can actually do', async ({
  page,
  market,
}) => {
  await paired(page, market);
  const response = await page.request.get(`${market.origin}/v1/capabilities`, api(market));
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.schema_version).toBe('1.0');
  expect(Array.isArray(body.sources)).toBe(true);
  expect(body.sources.length).toBeGreaterThan(0);
  const source = body.sources[0];
  // The truth fields the browser turns into badges.
  expect(source).toHaveProperty('venue_coverage');
  expect(source).toHaveProperty('realtime');
  expect(source).toHaveProperty('tradable_for_entry');
  // A delayed feed must never claim it can back an entry.
  if (source.realtime === false) {
    expect(source.tradable_for_entry).toBe(false);
  }
});

test('the indicator endpoint returns a series that names its venue', async ({
  page,
  market,
}) => {
  await paired(page, market);
  const response = await page.request.get(
    `${market.origin}/v1/indicators?instrument_id=${ID}&timeframe=1day&indicator=sma`,
    api(market),
  );
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.schema_version).toBe('1.0');
  expect(body.instrument_id).toBe(ID);
  expect(body.computed_by).toBe('local');
  // The venue is not optional: an indicator without it is not comparable.
  expect(body.source_coverage).not.toBe('unknown');
  const series = body.series ?? [];
  expect(Array.isArray(series)).toBe(true);
  for (const item of series) {
    expect(item.source_coverage).toBe(body.source_coverage);
    for (const point of item.points ?? []) {
      expect(point.source_coverage).toBe(body.source_coverage);
    }
  }
});

test('the indicator endpoint rejects an unknown indicator and a bad timeframe', async ({
  page,
  market,
}) => {
  await paired(page, market);
  const unknown = await page.request.get(
    `${market.origin}/v1/indicators?instrument_id=${ID}&timeframe=1day&indicator=nope`,
    api(market),
  );
  expect(unknown.status()).toBe(400);
  const badTimeframe = await page.request.get(
    `${market.origin}/v1/indicators?instrument_id=${ID}&timeframe=banana`,
    api(market),
  );
  expect(badTimeframe.status()).toBe(400);
});

test('the macro endpoint returns published observations with their release date', async ({
  page,
  market,
}) => {
  await paired(page, market);
  const response = await page.request.get(
    `${market.origin}/v1/macro?series_id=DGS10&as_of=2026-03-01`,
    api(market),
  );
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.schema_version).toBe('1.0');
  expect(body.as_of).toBe('2026-03-01');
  for (const point of body.points ?? []) {
    // A release date is what makes the observation usable, not a detail.
    expect(point.release_date).toBeTruthy();
    // An observation released after `as_of` was not public at that time.
    expect(point.release_date <= '2026-03-01').toBe(true);
    expect(point.observation_date <= point.release_date).toBe(true);
  }
});

test('the analysis endpoints refuse a request without a session', async ({
  page,
  market,
}) => {
  await page.goto(market.origin);
  for (const path of ['/v1/indicators', '/v1/macro', '/v1/capabilities']) {
    const response = await page.request.get(`${market.origin}${path}`, api(market));
    expect(response.status()).toBe(401);
  }
});

test('the analysis endpoints refuse a credential in the query string', async ({
  page,
  market,
}) => {
  await paired(page, market);
  const response = await page.request.get(
    `${market.origin}/v1/capabilities?token=secret`,
    api(market),
  );
  expect(response.status()).toBe(401);
});
