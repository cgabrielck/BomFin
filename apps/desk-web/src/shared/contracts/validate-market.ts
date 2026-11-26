import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import schema from './market.schema.json';
import type {
  MarketSnapshot,
  SnapshotFrame,
  UpdateFrame,
  ErrorFrame,
  SubscriptionKey,
} from './generated';

export type BrowserMarketFrame = SnapshotFrame | UpdateFrame | ErrorFrame;
const ajv = new Ajv2020({
  strictSchema: false,
  allErrors: false,
  validateFormats: true,
});
addFormats(ajv);
ajv.addFormat('decimal', {
  type: 'string',
  validate: (value: string) =>
    value.length <= 256 && /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value),
});
const nonzero = (value: string) => /[1-9]/.test(value.split(/[eE]/)[0]);
ajv.addKeyword({
  keyword: 'x-exclusiveMinimum',
  schemaType: 'string',
  type: 'string',
  validate: (bound: string, value: string) =>
    bound === '0' && !value.startsWith('-') && nonzero(value),
});
ajv.addKeyword({
  keyword: 'x-minimum',
  schemaType: 'string',
  type: 'string',
  validate: (bound: string, value: string) =>
    bound === '0' && (!value.startsWith('-') || !nonzero(value)),
});
const snapshotValidator = ajv.compile({
  ...schema,
  $ref: '#/$defs/MarketSnapshot',
});
const frameValidator = ajv.compile({
  ...schema,
  oneOf: ['SnapshotFrame', 'UpdateFrame', 'ErrorFrame'].map((name) => ({
    $ref: `#/$defs/${name}`,
  })),
});

function scoped(snapshot: MarketSnapshot, keys: SubscriptionKey[]) {
  const source = snapshot.health.source;
  if (snapshot.gap && snapshot.gap.source !== source)
    throw new Error('行情缺口來源不一致');
  for (const event of [...snapshot.quotes, ...snapshot.bars]) {
    const key = keys.find(
      (key) =>
        key.instrument_id === event.instrument_id && key.channel === event.kind,
    );
    if (
      !key ||
      event.payload.instrument_id !== event.instrument_id ||
      event.source !== source
    )
      throw new Error('行情股票或來源不一致');
    if (event.kind === 'quote' && event.payload.feed !== source)
      throw new Error('報價來源不一致');
    if (
      event.kind === 'bar' &&
      (!key.timeframe ||
        key.timeframe.count !== event.payload.timeframe.count ||
        key.timeframe.unit !== event.payload.timeframe.unit ||
        event.payload.source !== source)
    )
      throw new Error('圖表週期或來源不一致');
  }
}

export function parseSnapshot(
  value: unknown,
  keys: SubscriptionKey[],
): MarketSnapshot {
  if (!snapshotValidator(value)) throw new Error('行情資料格式不符');
  const snapshot = value as MarketSnapshot;
  scoped(snapshot, keys);
  return snapshot;
}

export function parseFrame(
  value: unknown,
  keys: SubscriptionKey[],
): BrowserMarketFrame {
  if (!frameValidator(value)) throw new Error('行情訊息格式不符');
  const frame = value as BrowserMarketFrame;
  if (frame.kind === 'snapshot') scoped(frame.payload, keys);
  if (frame.kind === 'update') {
    const event = frame.payload.event;
    // Reuse snapshot provenance checks; no new market fact is constructed.
    scoped(
      {
        schema_version: '1.0',
        epoch: frame.payload.epoch,
        cursor: frame.payload.sequence,
        as_of: frame.payload.processed_at,
        health: frame.payload.health,
        gap: frame.payload.gap,
        quotes: event?.kind === 'quote' ? [event] : [],
        bars: event?.kind === 'bar' ? [event] : [],
      },
      keys,
    );
    if (event?.kind === 'trade') throw new Error('瀏覽器通道未訂閱成交事件');
  }
  return frame;
}
