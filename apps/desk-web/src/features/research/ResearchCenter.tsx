import { useMemo, useState } from 'react';
import { useServerSession } from '../../app/ServerSession';
import { useResearchView, roleLabel, statusLabel } from './useResearchView';
import type {
  ResearchCheck,
  ResearchGraphResult,
  ResearchJobDetail,
  ResearchRole,
  ResearchRoleResult,
} from '../../shared/transport/research';

/**
 * The research centre.
 *
 * One panel serves both the research tab and the stock detail entry,
 * so a reader sees the same report in the same way wherever they open
 * it.
 *
 * The rule that shapes this panel is that a research conclusion is
 * only meaningful together with what it was allowed to see. So the
 * snapshot id, the `as_of` cut-off, the data quality and the evidence
 * ids travel with every conclusion. A finding without its evidence id
 * is not shown as a finding.
 *
 * The second rule is that absence is stated, never filled in. An
 * unconfigured model, a failed job, a rejected audit and missing
 * evidence each say so in words. Nothing here ever invents a report.
 */

export interface ResearchCenterProps {
  /** The instrument the research is about, when one is chosen. */
  instrumentId?: string | null;
  /** The symbol the reader sees, when one is chosen. */
  symbol?: string | null;
  /** True when the desk is showing sample data rather than the server. */
  demo?: boolean;
  /** A compact layout for the narrower stock detail column. */
  compact?: boolean;
}

/** The roles the reader can ask for, in the order the graph runs them. */
const ROLES: { value: ResearchRole | null; label: string }[] = [
  { value: null, label: '全流程（探索→技術→投資組合）' },
  { value: 'discovery', label: '探索 discovery' },
  { value: 'technical', label: '技術 technical' },
  { value: 'portfolio', label: '投資組合 portfolio' },
];

/** A verdict the harness can reach. */
const REJECTED_VERDICTS = new Set([
  'tool_forbidden',
  'output_schema_invalid',
  'snapshot_unknown',
  'snapshot_reference_broken',
  'budget_exceeded',
]);

export default function ResearchCenter({
  instrumentId = null,
  symbol = null,
  demo = false,
  compact = false,
}: ResearchCenterProps) {
  const session = useServerSession();
  const [role, setRole] = useState<ResearchRole | null>(null);
  const paired = session.mode === 'server' && session.status === 'paired';
  const enabled = !demo && paired;
  const view = useResearchView(enabled, instrumentId, session.expire);
  const configured = view.phase.phase === 'ready' || view.phase.phase === 'unconfigured';

  if (demo || session.mode !== 'server')
    return (
      <section className="research-center" aria-label="研究中心">
        <p className="eyebrow">RESEARCH CENTRE</p>
        <h3>研究中心</h3>
        <span className="pill amber" data-testid="research-demo">
          未接 AI · 示範資料
        </span>
        <p className="tiny" data-testid="research-demo-note">
          示範資料工作台 · 未接入 AI 模型。這個入口不會產生任何研究結論，也不會造出任何數字。
        </p>
        <ResearchDisclaimer />
      </section>
    );

  if (!paired)
    return (
      <section className="research-center" aria-label="研究中心">
        <p className="eyebrow">RESEARCH CENTRE</p>
        <h3>研究中心</h3>
        <span className="pill gray">需要登入</span>
        <p className="tiny" data-testid="research-unauthorized">
          研究服務需要登入；登入後才會顯示研究工作。
        </p>
        <ResearchDisclaimer />
      </section>
    );

  return (
    <section className="research-center" aria-label="研究中心">
      <div className="research-head">
        <div>
          <p className="eyebrow">RESEARCH CENTRE</p>
          <h3>研究中心</h3>
        </div>
        <span
          className={`pill ${view.phase.phase === 'unconfigured' ? 'amber' : 'gray'}`}
          data-testid="research-configured"
        >
          {view.phase.phase === 'unconfigured' ? 'AI 未配置' : 'AI 已配置'}
        </span>
      </div>

      {view.loading && (
        <p role="status" className="tiny">
          讀取研究服務狀態…
        </p>
      )}

      {view.phase.phase === 'unconfigured' && (
        <div className="notice" data-testid="research-unconfigured">
          <span className="notice-icon" aria-hidden="true">
            ◷
          </span>
          <div>
            <strong>研究模型尚未接入 · 明天可連接</strong>
            <p>
              {view.phase.reason ??
                '伺服器沒有設定研究模型的供應商，現在無法執行研究。'}
              。按鈕在接入前不會送出任何工作，也不會顯示任何示意結論。
            </p>
          </div>
        </div>
      )}

      {view.phase.phase === 'refused' && (
        <p className="tiny" data-testid="research-refused">
          {view.phase.message}；行情與 K 線不受影響。
        </p>
      )}

      {view.phase.phase === 'unavailable' && (
        <p role="alert" className="state-banner" data-testid="research-unavailable">
          {view.phase.message}
        </p>
      )}

      {configured && (
        <div className="research-launch">
          <label htmlFor="research-role">研究角色</label>
          <select
            id="research-role"
            aria-label="研究角色"
            value={role === null ? 'all' : role}
            onChange={(event) =>
              setRole(
                event.target.value === 'all'
                  ? null
                  : (event.target.value as ResearchRole),
              )
            }
          >
            {ROLES.map((item) => (
              <option key={item.value ?? 'all'} value={item.value ?? 'all'}>
                {item.label}
              </option>
            ))}
          </select>
          <button
            className="button"
            data-testid="research-start"
            disabled={
              !instrumentId ||
              view.submitting ||
              view.phase.phase === 'unconfigured'
            }
            onClick={() => {
              if (!instrumentId) return;
              void view.start(instrumentId, role);
            }}
          >
            {view.submitting ? '送出中…' : '發起研究'}
          </button>
          {symbol && (
            <span className="pill gray" data-testid="research-instrument">
              {symbol}
            </span>
          )}
          {!instrumentId && (
            <p className="tiny" data-testid="research-no-instrument">
              先選一檔股票才能發起研究；研究只針對已選標的。
            </p>
          )}
          {view.phase.phase === 'unconfigured' && (
            <p className="tiny" data-testid="research-disabled-note">
              模型接入前無法發起研究；面板仍可檢視狀態與既有工作。
            </p>
          )}
        </div>
      )}

      {view.problem && (
        <p role="alert" className="state-banner" data-testid="research-problem">
          {view.problem}
        </p>
      )}

      {view.jobs.length > 0 && (
        <div className="research-jobs">
          <h4>研究工作</h4>
          <ul className="research-job-list">
            {view.jobs.map((job) => (
              <li key={job.job_id}>
                <button
                  className="text-button"
                  data-testid={`research-job-${job.job_id}`}
                  onClick={() => view.watch(job.job_id)}
                >
                  {roleLabel(job.role)} · {statusLabel(job.status)} ·{' '}
                  {job.job_id.slice(0, 8)}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {view.active && (
        <JobReport detail={view.active} compact={compact} />
      )}

      {!view.active && view.jobs.length === 0 && configured && (
        <p className="tiny" data-testid="research-empty">
          還沒有研究工作。發起一次研究後，結論會連同快照、資料品質與證據一併顯示。
        </p>
      )}

      <ResearchDisclaimer />
    </section>
  );
}

/**
 * The standing note.
 *
 * A research conclusion is analysis, not an instruction. This panel
 * never places an order and never produces one, and saying so where
 * the reader is looking is cheaper than a disclaimer they ignore.
 */
function ResearchDisclaimer() {
  return (
    <p className="tiny research-disclaimer" data-testid="research-disclaimer">
      研究只產生分析結論，不會下單、不會讀取帳戶、不會替你做決定。任何入場決定都要另外經過風險審查。
    </p>
  );
}

/** One finished job, with everything it has to say for itself. */
function JobReport({
  detail,
  compact,
}: {
  detail: ResearchJobDetail;
  compact: boolean;
}) {
  const rejected = useMemo(
    () =>
      (detail.checks ?? []).filter((check) =>
        REJECTED_VERDICTS.has(check.execution_result),
      ),
    [detail.checks],
  );
  const results = useMemo(() => collectResults(detail), [detail]);
  const failed = detail.status === 'failed';
  return (
    <article className="research-report" data-testid="research-report">
      <div className="research-report-head">
        <span
          className={`pill ${failed ? 'amber' : 'gray'}`}
          data-testid="research-report-status"
        >
          {statusLabel(detail.status)}
        </span>
        <span className="pill gray" data-testid="research-report-role">
          {roleLabel(detail.role)}
        </span>
      </div>

      {failed && (
        <div role="alert" className="state-banner" data-testid="research-failed">
          研究工作失敗。
          {detail.reason ? `原因：${detail.reason}` : '伺服器沒有提供失敗原因。'}
          這個工作沒有結論可用。
        </div>
      )}

      {rejected.length > 0 && (
        <div
          role="alert"
          className="state-banner"
          data-testid="research-rejected"
        >
          審查拒收 {rejected.length} 項執行驗證
          {rejected[0].execution_result
            ? `：${rejected[0].execution_result}`
            : ''}
          {rejected[0].reasons?.length ? `（${rejected[0].reasons.join('；')}）` : ''}
          。被拒收的結果不會當成結論顯示。
        </div>
      )}

      <SnapshotMeta detail={detail} />

      {results.length === 0 && !failed && (
        <p className="tiny" data-testid="research-no-result">
          這個工作沒有可顯示的結論。
        </p>
      )}

      {results.map((result) => (
        <RoleResult key={result.role} result={result} />
      ))}

      {detail.checks && detail.checks.length > 0 && (
        <details className="research-checks" data-testid="research-checks">
          <summary>審查驗證 {detail.checks.length} 筆</summary>
          <ul>
            {detail.checks.map((check, index) => (
              <li key={`${check.role ?? 'unknown'}:${index}`}>
                <CheckLine check={check} />
              </li>
            ))}
          </ul>
        </details>
      )}

      {!compact && detail.result != null && (
        <details className="research-raw" data-testid="research-raw">
          <summary>原始報告</summary>
          <pre>{safeJson(detail.result)}</pre>
        </details>
      )}
    </article>
  );
}

/** The snapshot a conclusion is bound to. */
function SnapshotMeta({ detail }: { detail: ResearchJobDetail }) {
  const snapshot = detail.snapshot;
  const id = detail.snapshot_id ?? snapshot?.snapshot_id ?? null;
  if (!id)
    return (
      <p className="tiny" data-testid="research-no-snapshot">
        這個工作還沒有綁定快照；沒有快照就沒有可引用的證據。
      </p>
    );
  return (
    <div className="research-snapshot" data-testid="research-snapshot">
      <div>
        <span className="tiny">快照 snapshot_id</span>
        <code data-testid="research-snapshot-id">{id}</code>
      </div>
      {snapshot?.as_of && (
        <div>
          <span className="tiny">資料截止 as_of</span>
          <code data-testid="research-as-of">{snapshot.as_of}</code>
        </div>
      )}
      {snapshot?.data_quality && snapshot.data_quality.length > 0 && (
        <div>
          <span className="tiny">資料品質</span>
          <span data-testid="research-data-quality">
            {snapshot.data_quality.join('、')}
          </span>
        </div>
      )}
    </div>
  );
}

/** One role's conclusion, with the evidence it cites. */
function RoleResult({ result }: { result: ResearchRoleResult }) {
  const findings = result.findings ?? [];
  const missing = result.missing_data ?? [];
  return (
    <section className="research-role" data-testid={`research-role-${result.role}`}>
      <h4>{roleLabel(result.role)} 結論</h4>
      {findings.length === 0 && (
        <p className="tiny" data-testid={`research-role-${result.role}-empty`}>
          這個角色沒有產出任何結論。
        </p>
      )}
      <ul className="research-findings">
        {findings.map((finding, index) => (
          <li key={`${finding.evidence_id}:${index}`}>
            <p className="research-finding-text">{finding.text}</p>
            <span
              className="pill gray"
              data-testid={`research-evidence-${result.role}-${index}`}
            >
              證據 {finding.evidence_id}
            </span>
          </li>
        ))}
      </ul>
      {missing.length > 0 && (
        <details className="research-missing" data-testid="research-missing">
          <summary>缺少的資料 {missing.length} 項</summary>
          <ul>
            {missing.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

/** One harness verdict, in the words the backend used. */
function CheckLine({ check }: { check: ResearchCheck }) {
  const rejected = REJECTED_VERDICTS.has(check.execution_result);
  return (
    <span>
      <b data-testid={`research-check-${check.execution_result}`}>
        {check.role ?? '—'} · {check.execution_result}
      </b>
      {rejected ? '（拒收）' : '（通過）'}
      {check.model_version ? ` · ${check.model_version}` : ''}
      {check.checked_at ? ` · ${check.checked_at}` : ''}
      {check.reasons?.length ? ` · ${check.reasons.join('；')}` : ''}
    </span>
  );
}

/**
 * The role results a job holds.
 *
 * A single-role job carries one result object; a whole-graph job
 * carries a map of them. Both are read here so the panel does not have
 * to know which kind of job it is looking at.
 */
function collectResults(detail: ResearchJobDetail): ResearchRoleResult[] {
  const result = detail.result;
  if (!result) return [];
  const graph = result as ResearchGraphResult;
  if (graph.reports && typeof graph.reports === 'object')
    return Object.values(graph.reports).filter(
      (item): item is ResearchRoleResult =>
        !!item && typeof item === 'object' && 'role' in item,
    );
  const single = result as ResearchRoleResult;
  return 'role' in single ? [single] : [];
}

/** Print a raw report without letting it break the page. */
function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return '（原始報告無法序列化）';
  }
}
