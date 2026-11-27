import { useEffect, useRef, useState } from 'react';
import type { Bar } from '../../shared/contracts/generated';
import { createChartPort } from './chart-port';
import type { ChartPort } from './chart-port';
import type { ChartScope } from './bar-series';
import type { IndicatorLine } from './indicator-lines';

export default function ChartCanvas({
  bars,
  scope,
  indicators = [],
}: {
  bars: Bar[];
  scope: ChartScope;
  indicators?: IndicatorLine[];
}) {
  const container = useRef<HTMLDivElement>(null),
    port = useRef<ChartPort | null>(null);
  const [view, setView] = useState<Bar[]>([]),
    [error, setError] = useState(''),
    [indicatorError, setIndicatorError] = useState(''),
    [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const node = container.current;
    if (!node) return;
    let chart: ChartPort;
    try {
      chart = createChartPort(node, scope, setHover);
      port.current = chart;
    } catch {
      setError('圖表暫時無法建立');
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) chart.resize(rect.width, rect.height);
    });
    observer.observe(node);
    return () => {
      observer.disconnect();
      chart.dispose();
      port.current = null;
    };
  }, []);
  useEffect(() => {
    try {
      if (port.current) setView(port.current.applyBars(bars));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : '圖表資料無法顯示');
      setView([]);
      port.current?.dispose();
      port.current = null;
    }
  }, [bars]);
  useEffect(() => {
    try {
      if (port.current) port.current.applyIndicators(indicators);
      setIndicatorError('');
    } catch (failure) {
      // A chart that cannot draw the indicator still shows the candles.
      // The indicator values remain readable in the legend below it.
      setIndicatorError(
        failure instanceof Error ? failure.message : '指標疊圖無法顯示',
      );
    }
  }, [indicators]);
  if (error)
    return (
      <p role="status" className="state-banner">
        {error}；報價仍可獨立使用。
      </p>
    );
  const latest = view.at(-1),
    selected = view.find((bar) => Date.parse(bar.start) / 1000 === hover);
  return (
    <section aria-label="K 線圖" className="candle-workspace">
      <div className="chart-toolbar">
        <span>
          1 分鐘 · UTC · <b data-testid="chart-count">{view.length}</b> 根
        </span>
        <div>
          <button
            className="text-button"
            aria-label="放大圖表"
            onClick={() => port.current?.zoom(0.75)}
          >
            ＋
          </button>
          <button
            className="text-button"
            aria-label="縮小圖表"
            onClick={() => port.current?.zoom(1.3)}
          >
            －
          </button>
          <button className="text-button" onClick={() => port.current?.fit()}>
            重設圖表
          </button>
        </div>
      </div>
      {latest && (
        <p className="chart-values" aria-label="最新 K 線數值">
          最新 O {latest.open} · H {latest.high} · L {latest.low} · C{' '}
          <b data-testid="chart-last-close">{latest.close}</b> · V{' '}
          <b data-testid="chart-last-volume">{latest.volume ?? '—'}</b> ·{' '}
          {latest.status === 'forming'
            ? '形成中'
            : latest.status === 'corrected'
              ? '已修訂'
              : '已完成'}{' '}
          · 版本 {latest.revision}
        </p>
      )}
      <div className="candle-canvas" ref={container} />
      {indicatorError && (
        <p role="status" className="tiny" data-testid="indicator-draw-error">
          {indicatorError}；K 線不受影響。
        </p>
      )}
      {selected && (
        <p className="tiny">
          游標 {selected.start} · O {selected.open} H {selected.high} L{' '}
          {selected.low} C {selected.close} V {selected.volume ?? '未知'}
        </p>
      )}
      <p className="tiny">
        最後區間：{latest?.start} → {latest?.end}
        <br />
        來源：{scope.source} · 調整基準：{latest?.corporate_action_policy} ·{' '}
        {view.filter((bar) => bar.volume === null).length}{' '}
        根未提供成交量，不推算。
      </p>
      <details className="chart-data">
        <summary>檢視 K 線數值（最近 10 根）</summary>
        <div className="chart-table-scroll">
          <table>
            <thead>
              <tr>
                {['時間 UTC', '開', '高', '低', '收', '量'].map((label) => (
                  <th key={label}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {view.slice(-10).map((bar) => (
                <tr key={bar.start}>
                  <td>{bar.start}</td>
                  {[
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.volume ?? '—',
                  ].map((value, index) => (
                    <td key={index}>{value}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
