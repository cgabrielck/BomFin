import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useServerSession } from '../../app/ServerSession';
import type {
  MarketSnapshot,
  SubscriptionKey,
} from '../../shared/contracts/generated';
import { fetchSnapshot } from '../../shared/transport/market';
import type { StreamStatus } from '../../shared/transport/live';
import {snapshotTrace} from '../../shared/transport/market-trace';
import type {MarketTrace} from '../../shared/transport/market-trace';

export interface MarketViewState {
  trace?:MarketTrace;
  selectedInstrumentId: string | undefined;
  snapshot: MarketSnapshot | undefined;
  loading: boolean;
  error: Error | null;
  demo: boolean;
  resetId: string;
  streamStatus: StreamStatus | 'demo' | 'needs_pair';
}

export function useMarketSubscription(
  keys: SubscriptionKey[],
): MarketViewState {
  const session = useServerSession();
  const expire = useRef(session.expire);
  const resetCounter = useRef(0);
  expire.current = session.expire;
  const signature = JSON.stringify(keys);
  const [live, setLive] = useState<{
    trace?:MarketTrace;
    signature: string;
    snapshot?: MarketSnapshot;
    error: Error | null;
    status: StreamStatus;
    resetId: string;
  }>({ signature: '', error: null, status: 'connecting', resetId: '' });
  const identity = keys.map((key) => [
    key.instrument_id,
    key.channel,
    key.timeframe,
  ]);
  const query = useQuery({
    queryKey: ['demo-market', identity],
    queryFn: ({ signal }) => fetchSnapshot(keys, signal),
    enabled: session.mode === 'demo' && keys.length > 0,
  });
  useEffect(() => {
    if (session.mode !== 'server' || session.status !== 'paired') return;
    const selected = JSON.parse(signature) as SubscriptionKey[];
    if (!selected.length) return;
    const controller = new AbortController();
    let cancelStream: (() => void) | undefined,
      scheduled = 0,
      snapshot: MarketSnapshot | undefined,
      resetId = '';
    let trace:MarketTrace|undefined;
    setLive({ signature, error: null, status: 'connecting', resetId });
    const publish = () => {
      if (scheduled || controller.signal.aborted) return;
      scheduled = requestAnimationFrame(() => {
        scheduled = 0;
        if(trace&&trace.stateMono===undefined)trace={...trace,stateMono:performance.now()};
        if (!controller.signal.aborted)
          setLive((value) => ({
            ...value,
            snapshot,
            resetId,
            trace,
            ...(snapshot ? { error: null } : {}),
          }));
      });
    };
    const fail = (error: Error) => {
      if (controller.signal.aborted) return;
      snapshot = undefined;
      setLive({ signature, error, status: 'error', resetId: '' });
      if (error.name === 'SessionRequired') expire.current();
    };
    void import('../../shared/transport/live')
      .then(async (transport) => {
        snapshot = await transport.fetchSnapshot(selected, controller.signal);
        trace=snapshotTrace(snapshot);
        resetId = `${snapshot.epoch}:${++resetCounter.current}`;
        if (controller.signal.aborted) return;
        publish();
        cancelStream = transport.subscribeMarket(
          selected,
          (frame,incomingTrace) => {
            if (controller.signal.aborted || frame.kind === 'error') return;
            if(incomingTrace)trace=incomingTrace;
            if (frame.kind === 'snapshot') {
              snapshot = frame.payload;
              resetId = `${snapshot.epoch}:${++resetCounter.current}`;
            } else if (snapshot) {
              const update = frame.payload,
                event = update.event;
              let quotes = snapshot.quotes,
                bars = snapshot.bars;
              if (event?.kind === 'quote')
                quotes = [
                  ...quotes.filter(
                    (item) => item.instrument_id !== event.instrument_id,
                  ),
                  event,
                ];
              if (event?.kind === 'bar')
                bars = [
                  ...bars.filter(
                    (item) =>
                      !(
                        item.instrument_id === event.instrument_id &&
                        item.payload.start === event.payload.start &&
                        item.payload.timeframe.count ===
                          event.payload.timeframe.count &&
                        item.payload.timeframe.unit ===
                          event.payload.timeframe.unit
                      ),
                  ),
                  event,
                ].slice(-500);
              snapshot = {
                ...snapshot,
                epoch: update.epoch,
                cursor: update.sequence,
                as_of: update.processed_at,
                health: update.health,
                gap: update.gap,
                quotes,
                bars,
              };
            }
            publish();
          },
          controller.signal,
          (status) => {
            if (controller.signal.aborted) return;
            if (status === 'unauthorized') {
              snapshot = undefined;
              expire.current();
            }
            if (status === 'error') snapshot = undefined;
            setLive((value) => ({
              ...value,
              status,
              ...(status === 'unauthorized' ? { snapshot: undefined } : {}),
              ...(status === 'error'
                ? {
                    snapshot: undefined,
                    error: new Error('行情訊息驗證失敗，請重新連線'),
                  }
                : {}),
            }));
          },
        );
      })
      .catch((error) =>
        fail(error instanceof Error ? error : new Error('行情載入失敗')),
      );
    return () => {
      controller.abort();
      cancelStream?.();
      if (scheduled) cancelAnimationFrame(scheduled);
    };
  }, [signature, session.mode, session.status]);
  if (session.mode === 'server') {
    const visible = session.status === 'paired' && live.signature === signature;
    return {
      selectedInstrumentId: keys[0]?.instrument_id,
      snapshot: visible ? live.snapshot : undefined,
      loading:
        session.status === 'paired' &&
        (!visible || (!live.snapshot && !live.error)),
      error: visible ? live.error : null,
      demo: false,
      resetId: visible ? live.resetId : '',
      trace:visible?live.trace:undefined,
      streamStatus:
        session.status !== 'paired'
          ? 'needs_pair'
          : visible
            ? live.status
            : 'connecting',
    };
  }
  // No keepPreviousData: a different instrument never borrows the prior quote.
  return {
    selectedInstrumentId: keys[0]?.instrument_id,
    snapshot: query.data,
    loading: query.isPending,
    error: query.error,
    demo: true,
    resetId: `${query.data?.epoch ?? 'empty'}:${query.dataUpdatedAt}`,
    streamStatus: 'demo',
  };
}
