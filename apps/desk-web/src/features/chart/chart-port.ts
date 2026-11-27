import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  ColorType,
} from 'lightweight-charts';
import type { UTCTimestamp } from 'lightweight-charts';
import type { Bar } from '../../shared/contracts/generated';
import { BarSeries, drawingNumber } from './bar-series';
import type { ChartScope } from './bar-series';
import type { IndicatorLine } from './indicator-lines';

export interface ChartPort {
  applyBars(bars: Bar[]): Bar[];
  /**
   * Draw the indicator lines on the chart.
   *
   * The lines are replaced, not appended: a selection change must not
   * leave the previous indicator on the chart next to the new one.
   */
  applyIndicators(lines: IndicatorLine[]): void;
  resize(width: number, height: number): void;
  zoom(factor: number): void;
  fit(): void;
  dispose(): void;
}

/** The colour of each indicator line. */
const LINE_COLOURS: Record<string, string> = {
  sma: '#087f77',
  ema: '#2f6fb3',
  wma: '#7a5bbd',
  macd: '#b3701f',
  rsi: '#ac4741',
  atr: '#5b6b70',
  bollinger: '#8a6a3d',
  stochastic: '#a05a7a',
  macd_signal: '#7d8b90',
  macd_histogram: '#b0b8bb',
};

/** The colour used for an indicator this build does not name. */
const FALLBACK_COLOUR = '#5b6b70';


/** Only this adapter imports the plotting library. No market values are calculated here. */
export function createChartPort(
  container: HTMLElement,
  scope: ChartScope,
  onCrosshair: (time: number | null) => void,
): ChartPort {
  const chart = createChart(container, {
    width: container.clientWidth || 300,
    height: 360,
    layout: {
      background: { type: ColorType.Solid, color: '#ffffff' },
      textColor: '#65767b',
      attributionLogo: true,
    },
    grid: { vertLines: { color: '#f0f4f3' }, horzLines: { color: '#f0f4f3' } },
    timeScale: {
      timeVisible: true,
      secondsVisible: false,
      borderColor: '#e0e8e7',
    },
    rightPriceScale: { borderColor: '#e0e8e7' },
    handleScroll: { vertTouchDrag: false, horzTouchDrag: true },
    localization: { locale: 'zh-HK' },
  });
  const candles = chart.addSeries(CandlestickSeries, {
    upColor: '#087f77',
    downColor: '#ac4741',
    borderVisible: false,
    wickUpColor: '#087f77',
    wickDownColor: '#ac4741',
  });
  const volumes = chart.addSeries(
    HistogramSeries,
    {
      priceFormat: { type: 'volume' },
      priceLineVisible: false,
      lastValueVisible: false,
    },
    1,
  );
  chart.panes()[0].setStretchFactor(4);
  chart.panes()[1].setStretchFactor(1);
  // Pane 2 holds RSI and pane 3 holds MACD. Both live on their own
  // scale: RSI on a fixed 0-100 range, MACD around zero. Drawn against
  // a price axis they would be unreadable, and a chart that stretches
  // them to fit is wrong rather than merely crowded.
  //
  // The panes are kept even when empty. A pane that disappears when its
  // indicator is deselected would renumber the remaining panes, and the
  // next selection would land its line in the wrong pane.
  const rsiPane = chart.addPane(true);
  rsiPane.setStretchFactor(1);
  const macdPane = chart.addPane(true);
  macdPane.setStretchFactor(1);
  const PANE_INDEX: Record<string, number> = { price: 0, rsi: 2, macd: 3 };
  const book = new BarSeries(scope);
  let disposed = false,
    precision = 2;
  // The indicator lines currently drawn. They are replaced on every
  // selection change rather than appended, so a chart never shows the
  // previous indicator next to the new one.
  const indicatorSeries = new Map<
    string,
    ReturnType<typeof chart.addSeries>
  >();

  const time = (bar: Bar) => (Date.parse(bar.start) / 1000) as UTCTimestamp;
  const candle = (bar: Bar) => ({
    time: time(bar),
    open: drawingNumber(bar.open),
    high: drawingNumber(bar.high),
    low: drawingNumber(bar.low),
    close: drawingNumber(bar.close),
  });
  const volume = (bar: Bar) =>
    bar.volume === null
      ? { time: time(bar) }
      : {
          time: time(bar),
          value: drawingNumber(bar.volume, true),
          color:
            drawingNumber(bar.close) >= drawingNumber(bar.open)
              ? '#087f7770'
              : '#ac474170',
        };
  const crosshair = (event: { time?: unknown }) =>
    onCrosshair(typeof event.time === 'number' ? event.time : null);
  chart.subscribeCrosshairMove(crosshair);
  return {
    applyBars(bars) {
      if (disposed) throw new Error('圖表已關閉');
      const patch = book.applyBars(bars);
      const places = (value: string) => {
        const [part, exponent = '0'] = value.toLowerCase().split('e');
        return (part.split('.')[1]?.length ?? 0) - Number(exponent);
      };
      const required = Math.min(
        8,
        Math.max(
          2,
          ...bars.flatMap((bar) =>
            [bar.open, bar.high, bar.low, bar.close].map(places),
          ),
        ),
      );
      if (required !== precision) {
        precision = required;
        candles.applyOptions({
          priceFormat: { type: 'price', precision, minMove: 10 ** -precision },
        });
      }
      if (patch.reset) {
        candles.setData(patch.bars.map(candle));
        volumes.setData(patch.bars.map(volume));
        chart.timeScale().fitContent();
      } else
        for (const change of patch.changes) {
          candles.update(candle(change.bar), change.historical);
          volumes.update(volume(change.bar), change.historical);
        }
      return patch.bars;
    },
    applyIndicators(lines) {
      if (disposed) throw new Error('圖表已關閉');
      // Remove the previous selection first. A chart that keeps the old
      // line next to the new one shows two indicators where the reader
      // picked one.
      for (const series of indicatorSeries.values()) {
        chart.removeSeries(series);
      }
      indicatorSeries.clear();
      for (const line of lines) {
        const colour = LINE_COLOURS[line.indicator] ?? FALLBACK_COLOUR;
        if (line.style === 'histogram') {
          // A histogram is drawn as bars from a zero baseline. Its sign
          // is the signal, so a line would hide the crossings.
          const series = chart.addSeries(
            HistogramSeries,
            {
              priceFormat: { type: 'price', precision: 4, minMove: 0.0001 },
              priceLineVisible: false,
              lastValueVisible: false,
            },
            PANE_INDEX[line.pane] ?? 0,
          );
          series.setData(
            line.points.map((point) => ({
              time: point.time as UTCTimestamp,
              value: point.value,
              color:
                point.value >= 0 ? '#087f7770' : '#ac474170',
            })),
          );
          indicatorSeries.set(line.indicator, series);
          continue;
        }
        const series = chart.addSeries(
          LineSeries,
          {
            color: colour,
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
            title: line.indicator,
          },
          PANE_INDEX[line.pane] ?? 0,
        );
        series.setData(
          line.points.map((point) => ({
            time: point.time as UTCTimestamp,
            value: point.value,
          })),
        );
        indicatorSeries.set(line.indicator, series);
      }
      // RSI is bounded. Locking the scale keeps the reading comparable
      // between instruments; letting it auto-fit would make a flat RSI
      // look like a violent one. The lock applies only when RSI is
      // actually drawn, so an unused pane keeps its default scale.
      if (lines.some((line) => line.pane === 'rsi')) {
        const rsiScale = chart.priceScale('right', 2);
        rsiScale.applyOptions({
          autoScale: false,
          scaleMargins: { top: 0.05, bottom: 0.05 },
        });
        rsiScale.setVisibleRange({ from: 0, to: 100 });
      }
    },
    resize(width, height) {
      if (!disposed && width > 0 && height > 0)
        chart.resize(Math.floor(width), Math.floor(height));
    },
    zoom(factor) {
      const range = chart.timeScale().getVisibleLogicalRange();
      if (!disposed && range && factor > 0) {
        const width = Math.max(3, (range.to - range.from) * factor);
        chart
          .timeScale()
          .setVisibleLogicalRange({ from: range.to - width, to: range.to });
      }
    },
    fit() {
      if (!disposed) chart.timeScale().fitContent();
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      chart.unsubscribeCrosshairMove(crosshair);
      chart.remove();
    },
  };
}
