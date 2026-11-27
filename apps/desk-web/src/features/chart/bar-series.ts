import type { Bar, Timeframe } from '../../shared/contracts/generated';

export interface ChartScope {
  instrumentId: string;
  source: string;
  timeframe: Timeframe;
}
export interface BarPatch {
  reset: boolean;
  bars: Bar[];
  changes: { bar: Bar; historical: boolean }[];
}

/** Floating point is confined to display geometry; the original Bar stays exact. */
export function drawingNumber(value: string, allowZero = false): number {
  if (
    typeof value !== 'string' ||
    value.length > 256 ||
    !/^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value)
  )
    throw new Error('圖表數值格式不符');
  const number = Number(value);
  if (
    !Number.isFinite(number) ||
    number < 0 ||
    (!allowZero && number === 0) ||
    number > Number.MAX_SAFE_INTEGER ||
    (number > 0 && number < 1e-8)
  )
    throw new Error('數值超出圖表可安全顯示範圍');
  return number;
}
function decimalFact(value: string | null) {
  if (value === null) return null;
  const [mantissa, exponent = '0'] = value.toLowerCase().split('e');
  const [whole, fraction = ''] = mantissa.split('.');
  let digits = (whole + fraction).replace(/^0+/, '');
  let scale = Number(exponent) - fraction.length;
  if (!/[1-9]/.test(digits)) return '0';
  while (digits.endsWith('0')) {
    digits = digits.slice(0, -1);
    scale++;
  }
  return `${digits}e${scale}`;
}
const facts = (bar: Bar) =>
  JSON.stringify([
    Date.parse(bar.end),
    ...[bar.open, bar.high, bar.low, bar.close, bar.volume].map(decimalFact),
    bar.status,
    bar.revision,
    bar.session,
    bar.corporate_action_policy,
  ]);

/** Canonical bars in, drawing patches out. Volume is a replacement, never a sum. */
export class BarSeries {
  private values = new Map<number, Bar>();
  private initial = true;
  readonly scope: ChartScope;
  private retention: number;
  constructor(scope: ChartScope, retention = 500) {
    if (!Number.isInteger(retention) || retention < 1 || retention > 500)
      throw new Error('圖表容量無效');
    this.scope = scope;
    this.retention = retention;
  }
  applyBars(bars: Bar[]): BarPatch {
    if (bars.length > 500) throw new Error('圖表資料超出容量');
    if (!bars.length) {
      this.values.clear();
      this.initial = true;
      return { reset: true, bars: [], changes: [] };
    }
    const policy =
      this.values.values().next().value?.corporate_action_policy ??
      bars[0].corporate_action_policy;
    for (const bar of bars) {
      if (
        bar.instrument_id !== this.scope.instrumentId ||
        bar.source !== this.scope.source ||
        bar.timeframe.count !== this.scope.timeframe.count ||
        bar.timeframe.unit !== this.scope.timeframe.unit ||
        bar.corporate_action_policy !== policy
      )
        throw new Error('圖表股票、來源、週期或調整政策不一致');
      const prices = [bar.open, bar.high, bar.low, bar.close].map((value) =>
        drawingNumber(value),
      );
      if (bar.volume !== null) drawingNumber(bar.volume, true);
      if (
        prices[2] > Math.min(prices[0], prices[3]) ||
        prices[1] < Math.max(prices[0], prices[3]) ||
        ![
          bar.start,
          bar.end,
          bar.available_at,
          bar.received_at,
          bar.event_at,
        ].every((value) => Number.isFinite(Date.parse(value))) ||
        Date.parse(bar.start) >= Date.parse(bar.end) ||
        Date.parse(bar.available_at) < Date.parse(bar.received_at) ||
        !Number.isSafeInteger(bar.revision) ||
        bar.revision < 0
      )
        throw new Error('圖表 OHLC 或時間格式不符');
    }
    let reset = this.initial;
    const latest = Math.max(...this.values.keys(), -Infinity);
    const next = new Map(this.values);
    const changes: BarPatch['changes'] = [];
    for (const bar of bars) {
      const time = Date.parse(bar.start),
        previous = next.get(time);
      if (previous && previous.session !== bar.session)
        throw new Error('同一圖表時間存在不一致的市場時段');
      if (
        previous &&
        (bar.revision < previous.revision ||
          Date.parse(bar.available_at) < Date.parse(previous.available_at) ||
          (previous.status !== 'forming' && bar.status === 'forming'))
      )
        continue;
      if (previous && facts(previous) === facts(bar)) {
        next.set(time, bar);
        continue;
      }
      if (
        previous &&
        previous.status !== 'forming' &&
        previous.revision === bar.revision
      )
        throw new Error('已完成 K 線的同一修訂版本互相矛盾');
      if (!previous && time < latest) reset = true; // New historical interval needs insertion, not revision.
      next.set(time, bar);
      changes.push({ bar, historical: time < latest });
    }
    let ordered = [...next.values()].sort(
      (a, b) => Date.parse(a.start) - Date.parse(b.start),
    );
    // Compact occasionally rather than full setData at every rolling-window tick.
    if (ordered.length > this.retention * 2) {
      ordered = ordered.slice(-this.retention);
      reset = true;
    }
    this.values = new Map(ordered.map((bar) => [Date.parse(bar.start), bar]));
    this.initial = false;
    return {
      reset,
      bars: ordered,
      changes: changes.sort(
        (a, b) => Date.parse(a.bar.start) - Date.parse(b.bar.start),
      ),
    };
  }
}
