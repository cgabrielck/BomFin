import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  ColorType,
} from 'lightweight-charts';
import type { UTCTimestamp } from 'lightweight-charts';
import type { Bar } from '../../shared/contracts/generated';
import { BarSeries, drawingNumber } from './bar-series';
import type { ChartScope } from './bar-series';

export interface ChartPort {
  applyBars(bars: Bar[]): Bar[];
  resize(width: number, height: number): void;
  zoom(factor: number): void;
  fit(): void;
  dispose(): void;
}

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
  const book = new BarSeries(scope);
  let disposed = false,
    precision = 2;
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
