import { useEffect, useLayoutEffect, useState } from 'react';
import {commitQuoteTrace} from '../../shared/transport/market-trace';
import type { SubscriptionKey } from '../../shared/contracts/generated';
import { candidates, findCandidate } from './demo-catalog';
import type { Scenario } from './demo-catalog';
import { useMarketSubscription } from './useMarketSubscription';
import ChartPanel from '../chart/ChartPanel';
import MacroPanel from '../macro/MacroPanel';
import FeedCapabilityBadges from '../feed/FeedCapabilityBadges';
import ResearchCenter from '../research/ResearchCenter';

interface Props {
  symbol: string;
  scenario: Scenario;
  watch: Set<string>;
  toggleWatch: (s: string) => void;
  navigate: (s: string | null) => void;
  planned: (name: string) => void;
}
function ageLabel(event: string | null | undefined, now: number) {
  if (!event) return '來源時間未知';
  const ms = now - Date.parse(event);
  if (!Number.isFinite(ms) || ms < 0) return '來源時鐘待核對';
  const minutes = Math.floor(ms / 60000);
  return minutes >= 60
    ? `距來源 ${Math.floor(minutes / 60)} 小時 ${minutes % 60} 分`
    : `距來源 ${minutes} 分`;
}
export default function StockDetail({
  symbol,
  scenario,
  watch,
  toggleWatch,
  navigate,
  planned,
}: Props) {
  const candidate = findCandidate(symbol);
  const keys: SubscriptionKey[] = candidate
    ? [{ instrument_id: candidate.id, channel: 'quote', timeframe: null }]
    : [];
  const market = useMarketSubscription(keys);
  // The same quote reaches this reader over HTTP and again over the WebSocket.
  // The event id plus the epoch is the market event identity, so one event
  // yields one trace. A provider may reuse the id in a later epoch, so the
  // epoch has to travel with it.
  useLayoutEffect(()=>{
    if(market.trace&&market.trace.instrumentId===candidate?.id
      &&market.snapshot?.quotes.some(event=>event.event_id===market.trace!.eventId
        &&market.snapshot!.epoch===market.trace!.epoch))return commitQuoteTrace(market.trace);
  },[market.trace,candidate?.id]);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  if (!candidate)
    return (
      <div className="empty">
        <h1>不在示範股票清單</h1>
        <p>此版本沒有真實 symbol resolution，不會擅自換成其他股票。</p>
        <button className="button secondary" onClick={() => navigate(null)}>
          返回首頁
        </button>
      </div>
    );
  const quote = market.snapshot?.quotes.find(
    (event) => event.instrument_id === candidate.id,
  )?.payload;
  const point = quote?.last;
  const hiddenData =
    market.demo && (scenario === 'missing' || scenario === 'empty');
  const price = hiddenData ? '—' : (point?.price ?? '—');
  return (
    <section aria-label="股票詳情">
      <div className="heading">
        <div>
          <p className="eyebrow">EQUITY WORKSPACE</p>
          <h1>股票詳情</h1>
          <p>
            {market.demo
              ? '示範資料工作台 · 研究與行情服務尚未接入'
              : '只讀行情工作台 · 研究內容仍為設計示例'}
          </p>
        </div>
        <button className="button secondary" onClick={() => navigate(null)}>
          ← 機會總覽
        </button>
      </div>
      <div className="detail-grid">
        <aside className="stock-list" aria-label="示範股票清單">
          <h3>候選股票 · 示例</h3>
          {candidates.map((item) => (
            <button
              key={item.id}
              className={`stock-pick ${symbol === item.symbol ? 'active' : ''}`}
              aria-pressed={symbol === item.symbol}
              onClick={() => navigate(item.symbol)}
            >
              <span>
                {item.symbol}
                <small>{item.name}</small>
              </span>
            </button>
          ))}
        </aside>
        <div className="chart-panel">
          <div className="quote-head">
            <div>
              <h2>
                <span data-testid="selected-symbol">{symbol}</span>
                <span
                  className="muted"
                  style={{ fontSize: 12, fontWeight: 400 }}
                >
                  {' '}
                  {candidate.name}
                </span>
              </h2>
              <div className="price">
                <span data-testid="last-price">{price}</span>{' '}
                <small>USD · {market.demo ? '示範成交價' : '最近成交價'}</small>
              </div>
              <div className="bbo-quotes" aria-label="最佳買賣報價">
                {(['bid', 'ask'] as const).map(side => {
                  const value = hiddenData ? null : quote?.[side];
                  return (
                    <div className="bbo-side" key={side}>
                      <div>{side === 'bid' ? '買價 BID' : '賣價 ASK'} · USD</div>
                      <strong data-testid={`${side}-price`}>{value?.price ?? '—'}</strong>
                      <p className="tiny" data-testid={`${side}-source`}>
                        {ageLabel(value?.event_at, now)}<br />
                        來源時間：{value?.event_at ?? '未知'}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
            <span className="pill amber">即時權益未驗證</span>
          </div>
          {market.loading && (
            <p role="status" className="tiny">
              載入這檔股票的{market.demo ? '示範資料' : '行情'}…
            </p>
          )}
          {market.error && (
            <div role="alert" className="state-banner" data-testid="market-error">
              {market.error.message}；沒有套用其他股票的價格。
            </div>
          )}
          {!hiddenData && quote && (
            <p className="tiny" data-testid="market-source">
              來源：
              {market.demo
                ? '本機人工樣本'
                : market.snapshot?.health.source} ·{' '}
              {point ? ageLabel(point.event_at, now) : '無最近成交價'}
              <br />
              成交來源時間：{point?.event_at ?? '未知'} ·
              買賣報價與成交價分開顯示；即時權益未驗證，不可作入場依據。
            </p>
          )}
          {!market.demo && (
            <div
              className="tiny market-health"
              data-testid="market-health"
              role="status"
            >
              連線：
              {
                {
                  connecting: '連接中',
                  connected: '已連線',
                  recovering: '重新取得快照',
                  disconnected: '已斷線，顯示最後已知資料',
                  unauthorized: '登入失效',
                  error: '資料驗證失敗',
                  needs_pair: '等待登入',
                  demo: '示範',
                }[market.streamStatus]
              }
              <br />
              來源連線：
              {market.snapshot
                ? market.snapshot.health.connected
                  ? '連接中'
                  : '已斷線'
                : '未知'}{' '}
              · 缺口：
              {market.snapshot?.gap || market.snapshot?.health.gap_pending
                ? '未補齊'
                : market.snapshot
                  ? '未記錄缺口'
                  : '未知'}
              <br />
              報價品質：
              {market.snapshot?.quotes[0]?.payload.quality.join('、') ||
                '未知'}{' '}
              · 連線正常不代表價格新鮮。
            </div>
          )}
          <ChartPanel
            instrumentId={candidate.id}
            hidden={hiddenData}
            stale={market.demo && scenario === 'offline'}
          />
          <div className="tabs">
            <span className="tab active">觀察概況</span>
          </div>
          <p className="tiny">{candidate.why}</p>
          <p className="tiny">
            {market.demo
              ? '所有價格及觀點都是固定設計樣本，沒有即時市場結論。'
              : '報價來自已登入的行情來源；研究觀點仍為固定設計樣本。'}
          </p>
          <MacroPanel demo={market.demo} />
          <FeedCapabilityBadges demo={market.demo} />
        </div>
        <aside className="research-card">
          <p className="eyebrow">RESEARCH NOTE / SAMPLE</p>
          <h2>觀點與證據</h2>
          <span className="pill amber">{candidate.tag} · 設計示例</span>
          <h4>為何現在觀察</h4>
          <p>{candidate.why}</p>
          <h4>時間尺度</h4>
          <p>{candidate.horizon}</p>
          <details open>
            <summary>支持證據與反證</summary>
            <p>
              此處展示證據的位置，尚無實際研究來源；財務、估值與需求變化都需要獨立核對。
            </p>
          </details>
          <details>
            <summary>觀察／入場情境與失效條件</summary>
            <p>研究服務未接入，沒有入場價格、失效門檻或可執行方案。</p>
          </details>
          <details open>
            <summary>缺資料如何影響判斷</summary>
            <p>{candidate.missing}；目前不能據此作交易判斷。</p>
          </details>
          <button
            className="button secondary"
            aria-pressed={watch.has(symbol)}
            onClick={() => toggleWatch(symbol)}
          >
            {watch.has(symbol) ? '✓ 已加入自選' : '＋ 加入自選'}
          </button>
          <button className="text-button" onClick={() => planned('研究聊天')}>
            詢問這份觀點 ↗
          </button>
          {/*
            The real research entry. It uses the same shared component the
            research centre uses, so a reader sees the same report, the
            same snapshot metadata and the same audit verdicts wherever
            they open it.
          */}
          <details className="research-entry" data-testid="research-entry">
            <summary>發起研究 · {symbol}</summary>
            <ResearchCenter
              instrumentId={candidate.id}
              symbol={symbol}
              demo={market.demo}
              compact
            />
          </details>
        </aside>
      </div>
    </section>
  );
}
