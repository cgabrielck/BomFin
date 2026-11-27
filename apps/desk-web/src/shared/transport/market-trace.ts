import type {
  MarketSnapshot,
  MarketUpdate,
  QuoteMarketEvent,
  SubscriptionKey,
} from '../contracts/generated';

export interface MarketTrace {
  eventId: string;
  instrumentId: string;
  epoch: string;
  sequence: number;
  source: string;
  eventAt: string | null;
  providerReceivedAt: string;
  processedAt: string;
  receivedMono: number;
  receivedWall: number;
  stateMono?: number;
}
const snapshots = new WeakMap<MarketSnapshot, MarketTrace>();

/**
 * One quote event carries the identity of the delivery, not of the reader.
 * The same quote can arrive once over HTTP and again over the WebSocket, so the
 * event id alone cannot decide whether a frame is new. The subscribed keys
 * decide which quote this reader is allowed to trace: a bar subscriber must
 * never trace a quote event, and a reader of another instrument must not trace
 * this one.
 */
function quoteFor(
  value: MarketSnapshot | MarketUpdate,
  keys: SubscriptionKey[] | undefined,
): QuoteMarketEvent | undefined {
  const event = 'quotes' in value ? value.quotes[0] : value.event;
  if (event?.kind !== 'quote' || !event.payload.last) return;
  const quote = event as QuoteMarketEvent;
  if (
    keys &&
    keys.length &&
    !keys.some(
      (key) =>
        key.channel === 'quote' &&
        key.instrument_id === quote.instrument_id,
    )
  )
    return;
  return quote;
}

export function beginQuoteTrace(
  value: MarketSnapshot | MarketUpdate,
  receivedMono: number,
  receivedWall: number,
  keys?: SubscriptionKey[],
): MarketTrace | undefined {
  const quote = quoteFor(value, keys);
  if (!quote) return;
  return {
    eventId: quote.event_id,
    instrumentId: quote.instrument_id,
    epoch: value.epoch,
    sequence: 'cursor' in value ? value.cursor : value.sequence,
    source: quote.source,
    eventAt: quote.payload.last!.event_at,
    providerReceivedAt: quote.received_at,
    processedAt: 'as_of' in value ? value.as_of : value.processed_at,
    receivedMono,
    receivedWall,
  };
}
export function rememberSnapshot(
  snapshot: MarketSnapshot,
  mono: number,
  wall: number,
  keys?: SubscriptionKey[],
) {
  const trace = beginQuoteTrace(snapshot, mono, wall, keys);
  if (trace) snapshots.set(snapshot, trace);
}
export const snapshotTrace = (snapshot: MarketSnapshot) => snapshots.get(snapshot);

/**
 * A quote event id identifies the market event, not the render and not the
 * component instance. The HTTP snapshot and the WebSocket snapshot describe
 * the same event, and a reader that remounts would otherwise report a second
 * render for it. One market event therefore yields one trace per page, so a
 * re-delivery cannot inflate a latency sample or add a phantom event to a
 * measurement window.
 *
 * The claim pairs the event with its epoch. A provider may derive the event id
 * deterministically from the source facts, so the same id can legitimately
 * reappear once the coordinator has evicted its dedup evidence and a new epoch
 * is opened. Pairing with the epoch keeps those apart, while a re-delivery
 * inside one epoch still collapses onto the first trace.
 */
const committed = new Set<string>();
const MAX_CLAIMED = 500;

/**
 * The claim is taken when the measurement is dispatched, not when it is
 * scheduled. A cleanup that cancels the pending frames must not burn the event
 * id: the event would then never be measured at all.
 */
function claim(key: string): boolean {
  if (committed.has(key)) return false;
  committed.add(key);
  if (committed.size > MAX_CLAIMED) {
    // Bounded retention: the oldest claim is the least likely to be re-delivered.
    const oldest = committed.values().next();
    if (!oldest.done) committed.delete(oldest.value);
  }
  return true;
}

/** No global buffer, network export, auth data or price values. Rendered quotes only. */
export function commitQuoteTrace(trace: MarketTrace): () => void {
  const consumerMono = performance.now();
  let second = 0;
  let dispatched = false;
  const first = requestAnimationFrame(() => {
    second = requestAnimationFrame(() => {
      if (dispatched) return;
      dispatched = true;
      if (!claim(`${trace.epoch}|${trace.eventId}`)) return;
      const renderMono = performance.now();
      const sourceDelta =
        trace.eventAt === null
          ? null
          : Date.parse(trace.providerReceivedAt) - Date.parse(trace.eventAt);
      const providerDelta = trace.receivedWall - Date.parse(trace.providerReceivedAt);
      window.dispatchEvent(
        new CustomEvent('gabfin:market-trace', {
          detail: {
            ...trace,
            consumerMono,
            renderMono,
            sourceToProviderReceiveMs:
              sourceDelta !== null &&
              Number.isFinite(sourceDelta) &&
              sourceDelta >= 0
                ? sourceDelta
                : null,
            providerToBrowserReceiveMs:
              Number.isFinite(providerDelta) && providerDelta >= 0
                ? providerDelta
                : null,
            browserReceiveToRenderMs: renderMono - trace.receivedMono,
            // An unknown source clock is unknown skew, not a clean offset.
            clockSkew:
              sourceDelta === null ? null : providerDelta < 0 || sourceDelta < 0,
            renderBoundary: 'two-RAF paint opportunity',
          },
        }),
      );
    });
  });
  return () => {
    cancelAnimationFrame(first);
    if (second) cancelAnimationFrame(second);
  };
}
