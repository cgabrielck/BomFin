import { useMemo } from 'react';
import { fetchCapabilities } from '../../shared/transport/analysis';
import { useServerSession } from '../../app/ServerSession';
import { useAnalysis } from '../analysis/useAnalysis';

/**
 * The feed capability badges.
 *
 * Each badge answers one question a reader has before trusting a
 * number: what is this source, how fresh is it, what does it cost, and
 * can it be used to enter a position.
 *
 * The last question is the one that gets lost. A delayed or indicative
 * quote is still a quote, and it looks exactly like a real one on a
 * chart. So a source that cannot back an entry says so, in words, next
 * to its own name rather than in a footnote.
 */

/** How a delay reads in the badge. */
function delayText(realtime?: boolean, delayMinutes?: number | null): string {
  if (realtime === undefined) return '即時性未知';
  if (realtime) return '即時';
  if (delayMinutes === undefined || delayMinutes === null)
    return '非即時（延遲分鐘未知）';
  return `非即時 · 延遲 ${delayMinutes} 分`;
}

/** The fee class, in the words the contract uses. */
function feeText(feeClass?: string): string {
  switch (feeClass) {
    case 'none':
      return '免費';
    case 'exchange':
      return '交易所收費';
    case 'per_quote':
      return '按報價計費';
    case 'subscription':
      return '訂閱制';
    case undefined:
      return '費用未知';
    default:
      return feeClass;
  }
}

export interface FeedCapabilityBadgesProps {
  /** True when the desk is showing sample data rather than the server. */
  demo?: boolean;
}

/**
 * The badges.
 *
 * A source that was never measured does not appear. "We do not know"
 * and "we checked and it is fine" must not look the same, so the panel
 * shows only what the backend actually measured.
 */
export default function FeedCapabilityBadges({ demo = false }: FeedCapabilityBadgesProps) {
  const session = useServerSession();
  const enabled = !demo && session.mode === 'server' && session.status === 'paired';
  const view = useAnalysis(enabled ? 'capabilities' : null, fetchCapabilities);
  const sources = useMemo(
    () =>
      view.state.phase === 'ready' ? view.state.data.sources : [],
    [view.state],
  );
  if (demo || session.mode !== 'server')
    return (
      <section className="feed-capabilities" aria-label="行情來源能力">
        <h3>行情來源能力</h3>
        <p className="tiny" data-testid="capabilities-demo">
          示範資料工作台 · 未接入來源能力服務
        </p>
      </section>
    );
  if (session.status !== 'paired')
    return (
      <section className="feed-capabilities" aria-label="行情來源能力">
        <h3>行情來源能力</h3>
        <p className="tiny" data-testid="capabilities-unauthorized">
          來源能力需要登入；登入後才會顯示。
        </p>
      </section>
    );
  return (
    <section className="feed-capabilities" aria-label="行情來源能力">
      <h3>行情來源能力</h3>
      {view.loading && (
        <p role="status" className="tiny">
          載入來源能力…
        </p>
      )}
      {view.state.phase === 'missing' && (
        <p className="tiny" data-testid="capabilities-missing">
          {view.state.message}
        </p>
      )}
      {view.state.phase === 'unavailable' && (
        <p role="alert" className="state-banner" data-testid="capabilities-unavailable">
          {view.state.message}
        </p>
      )}
      {view.state.phase === 'invalid' && (
        <p role="alert" className="state-banner" data-testid="capabilities-invalid">
          {view.state.message}
        </p>
      )}
      {view.state.phase === 'refused' && (
        // A refusal is a standing condition, not an alarm. It must not
        // take the alert role, which would compete with the alerts that
        // do need a reader's attention.
        <p className="tiny" data-testid="capabilities-refused">
          {view.state.message}；行情與 K 線不受影響。
        </p>
      )}
      {sources.length > 0 && (
        <ul className="capability-list">
          {sources.map((source) => {
            const coverage = source.venue_coverage ?? '口徑未知';
            const tradable = source.tradable_for_entry;
            return (
              <li
                key={source.source}
                className="capability-item"
                data-testid={`capability-${source.source}`}
              >
                <div className="capability-head">
                  <strong>{source.source}</strong>
                  <span className="pill gray">口徑 {coverage}</span>
                  <span
                    className={`pill ${source.realtime ? '' : 'amber'}`}
                    data-testid={`capability-latency-${source.source}`}
                  >
                    {delayText(source.realtime, source.delay_minutes)}
                  </span>
                  <span className="pill gray" data-testid={`capability-fee-${source.source}`}>
                    {feeText(source.fee_class)}
                  </span>
                </div>
                {tradable === false && (
                  <p
                    className="capability-warning"
                    role="alert"
                    data-testid={`capability-warning-${source.source}`}
                  >
                    不可作為入場依據：這個來源只能供觀察，進場決策不能建立在它的報價上。
                  </p>
                )}
                {source.unavailable_reason !== undefined &&
                  source.unavailable_reason !== null && (
                    <p
                      className="capability-unavailable"
                      data-testid={`capability-reason-${source.source}`}
                    >
                      不可用原因：{source.unavailable_reason}
                    </p>
                  )}
                {source.depth_levels !== undefined &&
                  source.depth_levels !== null && (
                    <p className="tiny">
                      深度檔數：{source.depth_levels}
                      {source.latency_label ? ` · ${source.latency_label}` : ''}
                    </p>
                  )}
                {source.checked_at && (
                  <p className="tiny">量測時間：{source.checked_at}</p>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {sources.length === 0 && view.state.phase === 'ready' && (
        <p className="tiny" data-testid="capabilities-empty">
          尚未量測任何行情來源；未被探測過的來源不會出現在這裡。
        </p>
      )}
      <p className="tiny">
        口徑不同的來源，其量能指標（OBV／MFI／成交量均線）不可並列比較。
      </p>
    </section>
  );
}
