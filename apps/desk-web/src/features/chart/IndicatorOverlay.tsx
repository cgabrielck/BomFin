import { useEffect, useMemo, useState } from 'react';
import type { IndicatorStatus } from '../../shared/contracts/generated';
import { fetchIndicators } from '../../shared/transport/analysis';
import { useServerSession } from '../../app/ServerSession';
import { useAnalysis } from '../analysis/useAnalysis';
import { INDICATOR_GROUPS, toLines } from './indicator-lines';
import type { IndicatorGroup, IndicatorLine } from './indicator-lines';

/**
 * The indicator overlay on the chart.
 *
 * Two rules drive everything here.
 *
 * The first is that an indicator without a value is not drawn. A gap in
 * the line would read as "the value was zero that day", which is a
 * different and false claim. Instead the reason is shown in words.
 *
 * The second is that the values are the backend's strings. They arrive
 * as decimal strings and they are displayed as they came. Reformatting
 * them would put a number in front of the reader that the backend never
 * computed.
 */

/** The timeframe the overlay asks the backend for. */
const TIMEFRAME = '1min';

/** The reason an indicator has no value, in the words of the backend. */
function statusText(status: IndicatorStatus): string {
  const name = status.indicator.toUpperCase();
  if (status.reason === 'insufficient_history') {
    const required = status.required_bars;
    const observed = status.observed_bars;
    if (required !== undefined && observed !== undefined)
      return `${name} 需 ${required} 根，現有 ${observed} 根`;
    return `${name} 歷史長度不足`;
  }
  if (status.reason) return `${name}：${status.reason}`;
  return `${name} 暫無值`;
}

/** The group a status belongs to, so the reason lands under its toggle. */
function groupOf(status: IndicatorStatus): IndicatorGroup | undefined {
  return INDICATOR_GROUPS.find((group) =>
    group.names.includes(status.indicator),
  );
}

export interface IndicatorOverlayProps {
  /** The instrument whose history the indicators come from. */
  instrumentId: string;
  /** True when the desk is showing sample data rather than the server. */
  demo?: boolean;
  /** The lines the chart should draw, lifted to the chart by the parent. */
  onLines?: (lines: IndicatorLine[]) => void;
  /** The coverage of the candles, shown beside the indicator coverage. */
  candleCoverage?: string;
}

/**
 * The overlay itself.
 *
 * It fetches the indicator series, decides which lines exist, and
 * reports the reason for the ones that do not.
 */
export default function IndicatorOverlay({
  instrumentId,
  demo = false,
  onLines,
  candleCoverage,
}: IndicatorOverlayProps) {
  const session = useServerSession();
  const [selected, setSelected] = useState<string[]>([]);
  // The demo desk has no server behind it. Asking anyway would produce
  // an error that reads like a broken service rather than a desk that
  // was never connected.
  const enabled = !demo && session.mode === 'server' && session.status === 'paired';
  const wanted = useMemo(
    () => INDICATOR_GROUPS.filter((group) => selected.includes(group.label)),
    [selected],
  );
  const names = useMemo(
    () => wanted.flatMap((group) => group.names),
    [wanted],
  );
  // Every indicator is requested, not only the selected ones, because
  // the answer to "why is this indicator missing" only exists in the
  // status list. Requesting just the selected one would make an
  // unavailable indicator look like an unrequested one.
  //
  // The point limit keeps the response small enough to draw from: the
  // most recent points are the ones a reader looks at.
  const key = enabled ? `${instrumentId}:${TIMEFRAME}` : null;
  const view = useAnalysis(
    key,
    () => fetchIndicators(instrumentId, TIMEFRAME, undefined, 120),
  );
  const response =
    view.state.phase === 'ready' ? view.state.data : undefined;
  const lines = useMemo(
    () => (response ? toLines(response.series, names) : []),
    [response, names],
  );
  // The parent owns the chart, so the lines are handed up rather than
  // drawn here. A component that both fetched and drew would own two
  // concerns the reader cannot tell apart.
  useEffect(() => {
    onLines?.(lines);
  }, [lines, onLines]);

  if (demo)
    return (
      <section className="indicator-overlay" aria-label="指標疊圖">
        <p className="tiny" data-testid="indicator-demo">
          示範資料工作台 · 未接入指標服務
        </p>
      </section>
    );
  if (session.mode !== 'server')
    return (
      <section className="indicator-overlay" aria-label="指標疊圖">
        <p className="tiny" data-testid="indicator-demo">
          示範資料工作台 · 未接入指標服務
        </p>
      </section>
    );
  if (session.status !== 'paired')
    return (
      <section className="indicator-overlay" aria-label="指標疊圖">
        <p className="tiny" data-testid="indicator-unauthorized">
          指標服務需要登入；登入後才會顯示。
        </p>
      </section>
    );

  const statuses = response?.statuses ?? [];
  const shown = statuses.filter((status) => {
    const group = groupOf(status);
    return group ? selected.includes(group.label) : true;
  });
  const coverage = response?.source_coverage;
  return (
    <section className="indicator-overlay" aria-label="指標疊圖">
      <div className="indicator-controls">
        <span className="tiny">指標：</span>
        {INDICATOR_GROUPS.map((group) => (
          <button
            key={group.label}
            className={`text-button ${selected.includes(group.label) ? 'active' : ''}`}
            aria-pressed={selected.includes(group.label)}
            data-testid={`indicator-toggle-${group.label}`}
            onClick={() =>
              setSelected((current) =>
                current.includes(group.label)
                  ? current.filter((label) => label !== group.label)
                  : [...current, group.label],
              )
            }
          >
            {group.label}
          </button>
        ))}
      </div>
      {coverage && (
        <p className="tiny" data-testid="indicator-coverage">
          指標口徑：{coverage}
          {candleCoverage ? ` · K 線口徑：${candleCoverage}` : ''}
        </p>
      )}
      {lines.length > 0 && (
        <p className="tiny chart-indicators" aria-label="指標圖例">
          {lines.map((line) => {
            const last = line.points.at(-1);
            return (
              <span
                key={`${line.indicator}:${JSON.stringify(line.params)}`}
                data-testid={`indicator-legend-${line.indicator}`}
              >
                {line.indicator}
                {Object.keys(line.params).length > 0 && (
                  <sub>
                    {Object.entries(line.params)
                      .map(([key, value]) => `${key}=${value}`)
                      .join(',')}
                  </sub>
                )}{' '}
                {/* The backend's own string. The chart needs a number to
                    plot, but the reader gets the text the backend sent. */}
                <b>{last ? last.raw : '—'}</b>{' '}
                <span className="muted">({line.sourceCoverage})</span>
              </span>
            );
          })}
        </p>
      )}
      {view.loading && (
        <p role="status" className="tiny">
          載入指標…
        </p>
      )}
      {view.state.phase === 'missing' && (
        <p className="tiny" data-testid="indicator-missing">
          {view.state.message}；保留既有 K 線，不以其他標的或估算值補上。
        </p>
      )}
      {view.state.phase === 'unavailable' && (
        <p role="alert" className="state-banner" data-testid="indicator-unavailable">
          {view.state.message}；不顯示上一次的值當成新的。
        </p>
      )}
      {view.state.phase === 'invalid' && (
        <p role="alert" className="state-banner" data-testid="indicator-invalid">
          {view.state.message}
        </p>
      )}
      {view.state.phase === 'refused' && (
        // A refusal is a standing condition, not an alarm. It must not
        // take the alert role, which would compete with the alerts that
        // do need a reader's attention.
        <p className="tiny" data-testid="indicator-refused">
          {view.state.message}；K 線與其他行情不受影響。
        </p>
      )}
      {shown.length > 0 && (
        <ul className="indicator-statuses" data-testid="indicator-statuses">
          {shown.map((status) => (
            <li key={`${status.indicator}:${JSON.stringify(status.params)}`}>
              {statusText(status)}
            </li>
          ))}
        </ul>
      )}
      {response && response.series.length === 0 && statuses.length === 0 && (
        <p className="tiny" data-testid="indicator-empty">
          這段時間框架沒有可計算的指標序列。
        </p>
      )}
    </section>
  );
}
