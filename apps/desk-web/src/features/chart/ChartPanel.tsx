import { lazy, Suspense, useMemo, useState } from 'react';
import { useMarketSubscription } from '../market/useMarketSubscription';
import type { SubscriptionKey } from '../../shared/contracts/generated';
import IndicatorOverlay from './IndicatorOverlay';
import type { IndicatorLine } from './indicator-lines';
const ChartCanvas = lazy(() => import('./ChartCanvas'));
const TIMEFRAME = { count: 1, unit: 'minute' as const };

export default function ChartPanel({
  instrumentId,
  hidden = false,
  stale = false,
}: {
  instrumentId: string;
  hidden?: boolean;
  stale?: boolean;
}) {
  const keys: SubscriptionKey[] = hidden
    ? []
    : [{ instrument_id: instrumentId, channel: 'bar', timeframe: TIMEFRAME }];
  const market = useMarketSubscription(keys);
  // The indicator lines live here because the chart does. The overlay
  // fetches them and hands them up; the canvas draws them.
  const [indicators, setIndicators] = useState<IndicatorLine[]>([]);
  const snapshot = hidden ? undefined : market.snapshot;
  const bars = useMemo(
    () => snapshot?.bars.map((event) => event.payload) ?? [],
    [snapshot?.bars],
  );
  return (
    <div className="chart-content">
      {market.demo && bars.length > 0 && (
        <p className="chart-label">合成 K 線示範 · 非市場歷史資料</p>
      )}
      {stale && <p className="chart-label">離線情境 · 僅保留最後示範資料</p>}
      {!market.demo && (
        <p className="chart-label">
          K 線通道：
          {market.error
            ? '未接入／未獲授權'
            : market.streamStatus === 'connected'
              ? '已連線'
              : market.streamStatus === 'needs_pair'
                ? '等待登入'
                : '連線未確認'}{' '}
          · 缺口：
          {snapshot?.gap || snapshot?.health.gap_pending
            ? '未補齊'
            : snapshot
              ? '未記錄'
              : '未知'}
        </p>
      )}
      {bars.length > 0 ? (
        <Suspense fallback={<p role="status">載入圖表…</p>}>
          <ChartCanvas
            key={`${instrumentId}:${market.resetId}:${snapshot?.health.source}`}
            bars={bars}
            indicators={indicators}
            scope={{
              instrumentId,
              source: snapshot!.health.source,
              timeframe: TIMEFRAME,
            }}
          />
        </Suspense>
      ) : (
        <div className="empty chart-placeholder">
          <strong>尚無可靠 K 線資料</strong>
          <p>
            {market.error
              ? '此週期尚未接入、未獲授權或資料驗證失敗。'
              : '沒有具來源的 bar，圖表保持空白。'}{' '}
            不用 quote 拼 K 線或成交量。
          </p>
          {market.loading && !hidden && <p role="status">等待 K 線資料…</p>}
        </div>
      )}
      <IndicatorOverlay
        instrumentId={instrumentId}
        demo={market.demo}
        candleCoverage={snapshot?.health.source}
        onLines={setIndicators}
      />
      {bars.length > 0 && (
        <p className="chart-attribution tiny">
          圖表：
          <a
            href="https://www.tradingview.com/"
            target="_blank"
            rel="noreferrer"
          >
            TradingView Lightweight Charts™
          </a>{' '}
          · Copyright (с) 2025 TradingView, Inc. ·{' '}
          <a href="/third-party/lightweight-charts-LICENSE.txt">Apache 2.0</a>
        </p>
      )}
    </div>
  );
}
