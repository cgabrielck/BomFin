import type { MarketSnapshot, SubscriptionKey } from '../contracts/generated';
import { candidates } from '../../features/market/demo-catalog';

/** Demo HTTP transport only. No token, provider SDK, polling or trading endpoint. */
export async function fetchSnapshot(
  keys: SubscriptionKey[],
  signal?: AbortSignal,
): Promise<MarketSnapshot> {
  const isBar =
    keys.length === 1 &&
    keys[0].channel === 'bar' &&
    keys[0].timeframe?.count === 1 &&
    keys[0].timeframe.unit === 'minute';
  if (
    keys.length !== 1 ||
    (!isBar && (keys[0].channel !== 'quote' || keys[0].timeframe !== null))
  )
    throw new Error('此示範僅支援單股 quote 或 1 分鐘 K 線');
  const candidate = candidates.find(
    (item) => item.id === keys[0].instrument_id,
  );
  if (!candidate) throw new Error('示範股票不存在');
  const response = await fetch(
    `/demo/${isBar ? 'bars' : 'markets'}/${candidate.symbol}.json`,
    { signal },
  );
  if (!response.ok) throw new Error('示範資料暫時無法讀取');
  const data = (await response.json()) as MarketSnapshot;
  if (isBar) {
    if (data.health?.source !== 'demo') throw new Error('示範 K 線來源不一致');
    return (await import('../contracts/validate-market')).parseSnapshot(
      data,
      keys,
    );
  }
  // Boundary sanity checks, not a replacement for 04c's authenticated live API.
  if (
    data?.schema_version !== '1.0' ||
    data.health?.source !== 'demo' ||
    !Array.isArray(data.quotes) ||
    !Array.isArray(data.bars) ||
    data.quotes.some(
      (event) =>
        event.instrument_id !== candidate.id ||
        event.payload?.instrument_id !== candidate.id ||
        event.source !== 'demo',
    )
  )
    throw new Error('示範資料識別不一致');
  return data;
}

export async function fetchDemoAccount(
  signal?: AbortSignal,
): Promise<{ status: 'unavailable' }> {
  const response = await fetch('/demo/account.json', { signal });
  if (!response.ok) throw new Error('帳戶資料未接入');
  const data: unknown = await response.json();
  if (
    !data ||
    typeof data !== 'object' ||
    !('status' in data) ||
    data.status !== 'unavailable'
  )
    throw new Error('示範帳戶格式不符');
  return { status: 'unavailable' };
}
