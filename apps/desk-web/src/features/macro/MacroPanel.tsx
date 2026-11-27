import { useMemo, useState } from 'react';
import { fetchMacro } from '../../shared/transport/analysis';
import { useServerSession } from '../../app/ServerSession';
import { useAnalysis } from '../analysis/useAnalysis';

/**
 * The macro panel.
 *
 * The rule that shapes this panel is that a macro number without its
 * release date is worse than no number at all. A reader who sees "4.15"
 * cannot tell whether it describes last week or last quarter. So every
 * row shows the observation date and the release date together, and the
 * `as_of` filter the backend applies is never widened here.
 */

/** The date format the backend expects for `as_of`. */
const DATE = /^\d{4}-\d{2}-\d{2}$/;

export interface MacroPanelProps {
  /** True when the desk is showing sample data rather than the server. */
  demo?: boolean;
}

/**
 * The panel.
 *
 * The `as_of` date the reader picks is sent to the backend, and the
 * backend decides what was released by then. The panel does not filter
 * the response itself: a second filter in the browser could disagree
 * with the server's, and the server is the authority on what existed
 * when.
 */
export default function MacroPanel({ demo = false }: MacroPanelProps) {
  const session = useServerSession();
  const [asOf, setAsOf] = useState('');
  const enabled = !demo && session.mode === 'server' && session.status === 'paired';
  const key = enabled ? `macro:${asOf}` : null;
  const view = useAnalysis(
    key,
    () => fetchMacro(undefined, asOf || undefined),
  );
  const response = view.state.phase === 'ready' ? view.state.data : undefined;
  const points = useMemo(() => response?.points ?? [], [response]);
  if (demo || session.mode !== 'server')
    return (
      <section className="macro-panel" aria-label="宏觀面板">
        <h3>宏觀面板</h3>
        <p className="tiny" data-testid="macro-demo">
          示範資料工作台 · 未接入宏觀服務
        </p>
      </section>
    );
  if (session.status !== 'paired')
    return (
      <section className="macro-panel" aria-label="宏觀面板">
        <h3>宏觀面板</h3>
        <p className="tiny" data-testid="macro-unauthorized">
          宏觀服務需要登入；登入後才會顯示。
        </p>
      </section>
    );
  return (
    <section className="macro-panel" aria-label="宏觀面板">
      <h3>宏觀面板</h3>
      <form
        className="macro-asof"
        onSubmit={(event) => {
          event.preventDefault();
          const value = asOf.trim();
          if (value && !DATE.test(value)) return;
          setAsOf(value);
        }}
      >
        <label htmlFor="macro-as-of">截至日期 as_of</label>
        <input
          id="macro-as-of"
          type="date"
          value={asOf}
          onChange={(event) => setAsOf(event.target.value)}
        />
        <button className="text-button" type="submit">
          套用
        </button>
        {asOf && (
          <button
            className="text-button"
            type="button"
            onClick={() => setAsOf('')}
          >
            清除
          </button>
        )}
      </form>
      {response && (
        <p className="tiny" data-testid="macro-as-of">
          只顯示 {response.as_of} 當時已發布的觀測值；發布日期晚於此日期的值不會出現。
        </p>
      )}
      {view.loading && (
        <p role="status" className="tiny">
          載入宏觀資料…
        </p>
      )}
      {view.state.phase === 'missing' && (
        <p className="tiny" data-testid="macro-missing">
          {view.state.message}
        </p>
      )}
      {view.state.phase === 'unavailable' && (
        <p role="alert" className="state-banner" data-testid="macro-unavailable">
          {view.state.message}
        </p>
      )}
      {view.state.phase === 'invalid' && (
        <p role="alert" className="state-banner" data-testid="macro-invalid">
          {view.state.message}
        </p>
      )}
      {view.state.phase === 'refused' && (
        // A refusal is a standing condition, not an alarm. It must not
        // take the alert role, which would compete with the alerts that
        // do need a reader's attention.
        <p className="tiny" data-testid="macro-refused">
          {view.state.message}；行情與 K 線不受影響。
        </p>
      )}
      {points.length > 0 ? (
        <div className="macro-table-scroll">
          <table className="macro-table">
            <thead>
              <tr>
                <th>序列</th>
                <th>觀測日期</th>
                <th>發布日期</th>
                <th>數值</th>
                <th>單位</th>
                <th>頻率</th>
              </tr>
            </thead>
            <tbody>
              {points.map((point) => (
                <tr
                  key={`${point.series_id}:${point.observation_date}`}
                  data-testid={`macro-row-${point.series_id}`}
                >
                  <td>{point.series_id}</td>
                  <td>{point.observation_date}</td>
                  <td>{point.release_date}</td>
                  <td>
                    {/* The backend's own string, not a reformatted number. */}
                    <b>{point.value}</b>
                  </td>
                  <td>{point.units}</td>
                  <td>{point.frequency}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        view.state.phase === 'ready' && (
          <p className="tiny" data-testid="macro-empty">
            沒有已發布的觀測值。
          </p>
        )
      )}
    </section>
  );
}
