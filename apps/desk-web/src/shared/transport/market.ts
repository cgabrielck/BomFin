import type { MarketSnapshot, SubscriptionKey } from '../contracts/generated';
import { candidates } from '../../features/market/demo-catalog';

/** Demo HTTP transport only. No token, provider SDK, polling or trading endpoint. */
export async function fetchSnapshot(
  keys: SubscriptionKey[],
  signal?: AbortSignal,
): Promise<MarketSnapshot> {
  if (keys.length !== 1 || keys[0].channel !== 'quote' || keys[0].timeframe !== null)
    throw new Error('此示範僅支援單股 quote');
  const candidate = candidates.find((item) => item.id === keys[0].instrument_id);
  if (!candidate) throw new Error('示範股票不存在');
  const response = await fetch(`/demo/markets/${candidate.symbol}.json`, { signal });
  if (!response.ok) throw new Error('示範資料暫時無法讀取');
  const data = (await response.json()) as MarketSnapshot;
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

export async function fetchDemoAccount(signal?: AbortSignal): Promise<{ status: 'unavailable' }> {
  const response = await fetch('/demo/account.json', { signal });
  if (!response.ok) throw new Error('帳戶資料未接入');
  const data: unknown = await response.json();
  if (!data || typeof data !== 'object' || !('status' in data) || data.status !== 'unavailable')
    throw new Error('示範帳戶格式不符');
  return { status: 'unavailable' };
}
