import { test, expect } from './fixtures/secure-market';

test.use({ ignoreHTTPSErrors: true, trace: 'off' });

test('server overview resolves each list entry and opens registered research', async ({ page, market }) => {
  await page.route('**/v1/universe', route => route.fulfill({ json: { candidates: [] } }));
  await page.route('**/v1/universe/resolve', async route => {
    expect(route.request().postDataJSON()).toEqual({ symbols: 'AAPL MSFT !bad DENIED' });
    await route.fulfill({ json: { results: [
      { symbol: 'AAPL', name: 'Apple fixture', status: 'resolved', instrument_id: '11111111-1111-4111-8111-111111111111' },
      { symbol: 'MSFT', status: 'unknown', instrument_id: null },
      { symbol: '!BAD', status: 'invalid', instrument_id: null },
      { symbol: 'DENIED', status: 'unavailable', reason: 'rate_limited', instrument_id: null },
    ] } });
  });
  await page.route('**/v1/research/status', route => route.fulfill({ json: { configured: false, reason: 'model_not_configured' } }));
  await page.route('**/v1/research/jobs', route => route.fulfill({ json: { jobs: [] } }));
  await page.goto(market.origin);
  await page.getByRole('combobox', { name: '資料模式' }).selectOption('server');
  const { code } = await market.command('pair');
  await page.getByLabel('配對碼', { exact: true }).fill(String(code));
  await page.getByRole('button', { name: '配對登入', exact: true }).click();
  await expect(page.getByText('目前沒有有效候選')).toBeVisible();
  await page.getByLabel('美股代號', { exact: false }).fill('AAPL MSFT !bad DENIED');
  await page.getByRole('button', { name: '解析清單', exact: true }).click();
  await expect(page.getByText('Apple fixture', { exact: false })).toBeVisible();
  await expect(page.getByText('未知／尚未註冊')).toBeVisible();
  await expect(page.getByText('代號格式不支援')).toBeVisible();
  await expect(page.getByText('供應商速率限制，請稍後重試')).toBeVisible();
  await page.getByRole('button', { name: '開啟研究 ↗' }).click();
  await expect(page.getByTestId('research-start')).toBeDisabled();
});
