import { useQuery } from '@tanstack/react-query';
import type { MarketSnapshot, SubscriptionKey } from '../../shared/contracts/generated';
import { fetchSnapshot } from '../../shared/transport/market';

export interface MarketViewState {
  selectedInstrumentId: string | undefined;
  snapshot: MarketSnapshot | undefined;
  loading: boolean;
  error: Error | null;
  demo: true;
}

export function useMarketSubscription(keys: SubscriptionKey[]): MarketViewState {
  const identity = keys.map((key) => [key.instrument_id, key.channel, key.timeframe]);
  const query = useQuery({
    queryKey: ['demo-market', identity],
    queryFn: ({ signal }) => fetchSnapshot(keys, signal),
    enabled: keys.length > 0,
  });
  // No keepPreviousData: a different instrument never borrows the prior quote.
  return {
    selectedInstrumentId: keys[0]?.instrument_id,
    snapshot: query.data,
    loading: query.isPending,
    error: query.error,
    demo: true,
  };
}
