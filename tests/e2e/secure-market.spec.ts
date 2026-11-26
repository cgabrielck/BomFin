import { test, expect } from './fixtures/secure-market';
import type { Page } from '@playwright/test';

async function paired(
  page: Page,
  market: {
    origin: string;
    command: (action: string) => Promise<Record<string, unknown>>;
  },
) {
  await page.goto(market.origin);
  await page.getByRole('combobox', { name: '資料模式' }).selectOption('server');
  await expect(
    page.getByRole('heading', { name: '登入行情工作台' }),
  ).toBeVisible();
  const { code } = await market.command('pair');
  await page.getByLabel('配對碼', { exact: true }).fill(String(code));
  await page.getByRole('button', { name: '配對登入', exact: true }).click();
  await expect(
    page.getByRole('button', { name: '登出', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'AAPL ↗', exact: true }).click();
  await expect(page.getByTestId('last-price')).toHaveText('210.00');
  await expect(page.getByTestId('market-health')).toContainText('連線：已連線');
}

// Self-signed certificate exception is confined to this test context.
test.use({ ignoreHTTPSErrors: true, trace: 'off' });

test('server mode requires pairing and receives private TLS market state', async ({
  page,
  market,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(market.origin);
  await page.getByRole('combobox', { name: '資料模式' }).selectOption('server');
  await expect(
    page.getByRole('heading', { name: '登入行情工作台' }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath('pairing-desktop.png'),
    fullPage: true,
  });
  const { code } = await market.command('pair');
  await page.getByLabel('配對碼', { exact: true }).fill(String(code));
  await page.getByRole('button', { name: '配對登入', exact: true }).click();
  await page.getByRole('button', { name: 'AAPL ↗', exact: true }).click();
  await expect(page.getByTestId('last-price')).toHaveText('210.00');
  await market.command('price', { symbol: 'AAPL', price: '211.25' });
  await expect(page.getByTestId('last-price')).toHaveText('211.25');
  await expect(page.getByTestId('market-source')).toContainText('fixture');
  await page.screenshot({
    path: testInfo.outputPath('market-desktop.png'),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: testInfo.outputPath('market-mobile.png'),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  ).toBe(false);
});

test('logout clears the quote before network confirmation', async ({
  page,
  market,
}) => {
  await paired(page, market);
  let requested!: () => void, release!: () => void;
  const started = new Promise<void>((resolve) => (requested = resolve));
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route('**/logout', async (route) => {
    requested();
    await held;
    await route.continue().catch(() => {});
  });
  try {
    await page.getByRole('button', { name: '登出', exact: true }).click();
    await started;
    await expect(page.getByTestId('last-price')).toHaveText('—');
    await expect(
      page.getByRole('heading', { name: '登入行情工作台' }),
    ).toBeVisible();
  } finally {
    release();
  }
});

test('quiet expired session clears prices and reconnects with a new pairing', async ({
  page,
  market,
}) => {
  await paired(page, market);
  await market.command('expire');
  await expect(
    page.getByRole('heading', { name: '登入行情工作台' }),
  ).toBeVisible();
  await expect(page.getByTestId('last-price')).toHaveText('—');
  const { code } = await market.command('pair');
  await page.getByLabel('配對碼', { exact: true }).fill(String(code));
  await page.getByRole('button', { name: '配對登入', exact: true }).click();
  await expect(page.getByTestId('last-price')).toHaveText('210.00');
  await expect(page.getByTestId('market-health')).toContainText('連線：已連線');
});

test('expired session still clears prices when the close code is a generic transport error', async ({
  page,
  market,
}) => {
  await page.routeWebSocket('**/market/stream', (route) => {
    const server = route.connectToServer();
    server.onClose(() => route.close({ code: 1011 }));
  });
  await paired(page, market);
  await market.command('expire');
  await expect(
    page.getByRole('heading', { name: '登入行情工作台' }),
  ).toBeVisible();
  await expect(page.getByTestId('last-price')).toHaveText('—');
});

test('reload restores same-origin session without storing tokens and logout revokes it', async ({
  page,
  market,
}) => {
  await paired(page, market);
  await page.reload();
  await page.getByRole('combobox', { name: '資料模式' }).selectOption('server');
  await expect(page.getByTestId('last-price')).toHaveText('210.00');
  expect(
    await page.evaluate(() => ({
      local: localStorage.length,
      session: sessionStorage.length,
      hasAuth: document.cookie.includes('gabfin_session='),
    })),
  ).toEqual({ local: 0, session: 0, hasAuth: false });
  await page.getByRole('button', { name: '登出', exact: true }).click();
  await expect(page.getByTestId('last-price')).toHaveText('—');
  await expect
    .poll(async () =>
      (await page.request.get(market.origin + '/session')).status(),
    )
    .toBe(401);
});

test('late server snapshot cannot replace a newer selected instrument', async ({
  page,
  market,
}) => {
  await paired(page, market);
  let requested!: () => void, release!: () => void;
  const started = new Promise<void>((resolve) => (requested = resolve)),
    held = new Promise<void>((resolve) => (release = resolve));
  await page.route('**/market/snapshot', async (route) => {
    const keys = route.request().postDataJSON().keys;
    if (keys[0].instrument_id.startsWith('2222')) {
      requested();
      await held;
    }
    await route.continue().catch(() => {});
  });
  await page.getByRole('button', { name: /^MSFT Microsoft/ }).click();
  await started;
  await page.getByRole('button', { name: /^NVDA NVIDIA/ }).click();
  await expect(page.getByTestId('last-price')).toHaveText('140.00');
  release();
  await market.command('price', { symbol: 'MSFT', price: '999.00' });
  await expect(page.getByTestId('selected-symbol')).toHaveText('NVDA');
  await expect(page.getByTestId('last-price')).toHaveText('140.00');
});

test('provider gap is visible despite an open browser connection', async ({
  page,
  market,
}) => {
  await paired(page, market);
  await market.command('gap');
  await expect(page.getByTestId('market-health')).toContainText('缺口：未補齊');
  await expect(page.getByTestId('market-health')).toContainText(
    '來源連線：已斷線',
  );
  await expect(page.getByTestId('last-price')).toHaveText('210.00');
});

test('canonical validation refuses a foreign instrument in an HTTP snapshot', async ({
  page,
  market,
}) => {
  await paired(page, market);
  await page.route('**/market/snapshot', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    if (!body.quotes?.length) {
      await route.fulfill({ response });
      return;
    }
    body.quotes[0].instrument_id = '11111111-1111-4111-8111-111111111111';
    await route.fulfill({ response, json: body });
  });
  await page.getByRole('button', { name: /^MSFT Microsoft/ }).click();
  await expect(page.getByTestId('last-price')).toHaveText('—');
  await expect(page.getByRole('alert')).toContainText('行情股票或來源不一致');
});

for (const failure of ['snapshot_required', 'slow_consumer', 'sequence_hole']) {
  test(`${failure} recovers from a new full snapshot`, async ({
    page,
    market,
  }) => {
    let connections = 0,
      injected = false;
    const firstFrames: string[] = [];
    await page.routeWebSocket('**/market/stream', (route) => {
      const index = connections++;
      const server = route.connectToServer();
      let first = true;
      server.onMessage((message) => {
        const frame = JSON.parse(String(message));
        if (first) {
          firstFrames[index] = frame.kind;
          first = false;
        }
        if (
          !injected &&
          frame.kind === 'update' &&
          frame.payload.event?.kind === 'quote'
        ) {
          injected = true;
          if (failure === 'sequence_hole') {
            frame.payload.sequence += 2;
            route.send(JSON.stringify(frame));
          } else
            route.send(
              JSON.stringify({ version: 1, kind: 'error', code: failure }),
            );
        } else route.send(message);
      });
    });
    await paired(page, market);
    await market.command('price', { symbol: 'AAPL', price: '212.50' });
    await expect(page.getByTestId('last-price')).toHaveText('212.50');
    await expect(page.getByTestId('market-health')).toContainText(
      '連線：已連線',
    );
    expect(injected).toBe(true);
    expect(connections).toBe(2);
    expect(firstFrames).toEqual(['snapshot', 'snapshot']);
  });
}
