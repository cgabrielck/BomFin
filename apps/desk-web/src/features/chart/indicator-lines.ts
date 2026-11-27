import type { IndicatorSeries } from '../../shared/contracts/generated';

/**
 * The indicator lines one chart draws.
 *
 * An indicator line is a run of points with its own scale, and the scale
 * is not always the price scale: RSI lives on a fixed 0-100 range and
 * MACD lives around zero. Each line therefore declares the pane it
 * belongs to, so a chart can put it where it is readable.
 */

/**
 * The panes an indicator line can live in.
 *
 * `price` shares the candle scale. `rsi` gets a pane locked to 0-100.
 * `macd` gets its own pane so a MACD reading is never stretched against
 * a price axis it has nothing to do with.
 */
export type IndicatorPane = 'price' | 'rsi' | 'macd';

/**
 * The indicator groups a chart can toggle.
 *
 * A group is what the reader picks. The group maps to the canonical
 * indicator names the backend produces, so selecting "MACD" draws the
 * MACD line, its signal and its histogram rather than a partial line
 * that looks like a complete one.
 */
export interface IndicatorGroup {
  /** The label the toggle shows. */
  label: string;
  /** The canonical indicator names this group covers. */
  names: string[];
  /** The pane the group's lines belong to. */
  pane: IndicatorPane;
}

export const INDICATOR_GROUPS: IndicatorGroup[] = [
  { label: 'SMA20', names: ['sma'], pane: 'price' },
  { label: 'EMA20', names: ['ema'], pane: 'price' },
  { label: 'BOLL', names: ['bollinger_upper', 'bollinger_middle', 'bollinger_lower'], pane: 'price' },
  { label: 'VWAP', names: ['vwap'], pane: 'price' },
  { label: 'RSI14', names: ['rsi'], pane: 'rsi' },
  { label: 'MACD', names: ['macd', 'macd_signal', 'macd_histogram'], pane: 'macd' },
  { label: 'ATR14', names: ['atr'], pane: 'price' },
];

/**
 * The indicators that belong on their own scale rather than on the
 * price scale.
 *
 * RSI is bounded, MACD is centred on zero, and both are meaningless
 * drawn against a price. Putting them on the price pane would make the
 * chart wrong rather than merely crowded.
 */
const PANE_BY_INDICATOR: Record<string, IndicatorPane> = {
  rsi: 'rsi',
  macd: 'macd',
  macd_signal: 'macd',
  macd_histogram: 'macd',
  stochastic_k: 'macd',
  stochastic_d: 'macd',
  stochastic_j: 'macd',
  mfi: 'macd',
};

/**
 * The indicators drawn as bars from a zero baseline.
 *
 * A histogram's sign is the signal. Drawing it as a line would turn the
 * crossings into invisible wiggles.
 */
const HISTOGRAM_INDICATORS = new Set(['macd_histogram']);

/** One indicator line, ready to be drawn. */
export interface IndicatorLine {
  /** The indicator name, as the contract spells it. */
  indicator: string;
  /** The parameter set, as the contract spells it. */
  params: Record<string, string>;
  /**
   * How the line is drawn.
   *
   * A histogram is not a line. Its sign carries the meaning, and
   * joining the points with a line would hide the crossings.
   */
  style: 'line' | 'histogram';
  /** The pane this line belongs to. */
  pane: IndicatorPane;
  /**
   * The points, in time order.
   *
   * `raw` is the backend's string and is what gets displayed. `value`
   * is the same number parsed for the chart library, which needs a
   * number to plot. The two are kept apart so the reader always sees
   * the backend's own text.
   */
  points: { time: number; value: number; raw: string }[];
  /** The source coverage the values were computed from. */
  sourceCoverage: string;
}

/**
 * The lines a chart should draw for one selection.
 *
 * A series with no points produces no line. A line with no points would
 * draw an axis and a legend entry for nothing, which is how a reader
 * comes to believe a value exists when it does not.
 */
export function toLines(
  series: IndicatorSeries[],
  selection: string[],
): IndicatorLine[] {
  const wanted = new Set(selection);
  // An empty selection draws nothing. Drawing everything would put
  // twenty-four indicators on the chart and make the reader pick one
  // anyway, only with less control over it.
  if (!wanted.size) return [];
  const lines: IndicatorLine[] = [];
  for (const item of series) {
    if (!wanted.has(item.indicator)) continue;
    const points = item.points.flatMap((point) => {
      // A null value is no value. `Number(null)` is 0, and plotting a
      // zero there would claim the indicator read exactly zero that
      // minute, which is a different and false statement.
      if (point.value === null) return [];
      const time = Date.parse(point.event_at) / 1000;
      const value = Number(point.value);
      if (!Number.isFinite(time) || !Number.isFinite(value)) return [];
      return [{ time, value, raw: point.value }];
    });
    if (!points.length) continue;
    points.sort((a, b) => a.time - b.time);
    lines.push({
      indicator: item.indicator,
      params: item.params,
      pane: PANE_BY_INDICATOR[item.indicator] ?? 'price',
      style: HISTOGRAM_INDICATORS.has(item.indicator) ? 'histogram' : 'line',
      points,
      sourceCoverage: item.source_coverage,
    });
  }
  return lines;
}

/**
 * The label a line shows in the legend.
 *
 * The parameters are part of the identity: "SMA" and "SMA20" are
 * different lines and a legend that shows only the name hides the
 * difference.
 */
export function lineLabel(line: IndicatorLine): string {
  const parts = Object.entries(line.params).map(([key, value]) => `${key}=${value}`);
  return parts.length ? `${line.indicator}(${parts.join(',')})` : line.indicator;
}
