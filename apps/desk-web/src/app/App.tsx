import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import HomePage from '../features/market/HomePage';
import { findCandidate } from '../features/market/demo-catalog';
import type { Scenario } from '../features/market/demo-catalog';
import { PlannedDialog } from '../shared/ui/PlannedDialog';
import { useRoute } from './useRoute';
import { PairingPanel, SourceControl, useServerSession } from './ServerSession';

const StockDetail = lazy(() => import('../features/market/StockDetail'));
const ResearchCenter = lazy(() => import('../features/research/ResearchCenter'));
const CandidateWorkspace = lazy(() => import('../features/market/CandidateWorkspace'));

/**
 * The desk's own tabs.
 *
 * These live beside the route rather than inside it: `useRoute` owns
 * the instrument, and the research centre is a workspace that can be
 * opened on its own or next to a stock. Putting it in the hash would
 * make every existing route assertion depend on a new URL shape.
 */
type Workspace = 'overview' | 'research' | 'stock';
const scenarioMessages: Record<Scenario, string> = {
  sample: '',
  offline: '離線情境：保留最後示範資料並標記為舊價；沒有新的市場資料。',
  missing: '缺資料情境：沒有報價或 K 線，研究只能呈現資料缺口。',
  empty: '空清單情境：沒有候選，仍可搜尋或重設。',
};

export default function App() {
  const session = useServerSession();
  const demo = session.mode === 'demo';
  const { symbol, navigate } = useRoute();
  const [search, setSearch] = useState('');
  const [scenario, setScenario] = useState<Scenario>('sample');
  const [watch, setWatch] = useState<Set<string>>(() => new Set());
  const [planned, setPlanned] = useState<string | null>(null);
  // The research centre is a local tab, so opening it never changes the
  // hash and never invalidates the instrument the reader already chose.
  const [tab, setTab] = useState<Workspace>('overview');
  const [listSelection, setListSelection] = useState<{ id: string; symbol: string } | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  // A route change made from elsewhere — a deep link, or the home page's
  // stock cards — brings the stock workspace back with it. The research
  // tab is never overridden this way, because it never changes the hash.
  useEffect(() => {
    setTab(symbol ? 'stock' : 'overview');
    setListSelection(null);
  }, [symbol]);
  const toggleWatch = (value: string) =>
    setWatch((previous) => {
      const next = new Set(previous);
      next.has(value) ? next.delete(value) : next.add(value);
      return next;
    });
  const reset = () => {
    setSearch('');
    setScenario('sample');
  };
  return (
    <>
      <div className="preview">
        <div>
          <strong>GABFIN / {demo ? '示範工作台' : '行情工作台'}</strong>　
          {demo
            ? '固定示例 · 未接行情、AI 或帳戶'
            : '行情獨立登入 · 研究卡仍為示例'}
        </div>
        <div className="preview-controls">
          <SourceControl />
          {demo && (
            <>
              <label htmlFor="scenario">示範情境</label>
              <select
                id="scenario"
                aria-label="示範情境"
                value={scenario}
                onChange={(event) =>
                  setScenario(event.target.value as Scenario)
                }
              >
                <option value="sample">示範／部分報告</option>
                <option value="offline">離線／舊資料</option>
                <option value="missing">行情缺資料</option>
                <option value="empty">空清單</option>
              </select>
            </>
          )}
        </div>
      </div>
      <div className="app">
        <aside className="sidebar" aria-label="主導航">
          <div className="brand">
            gabfin<i>.</i>
            <small>RESEARCH WORKSPACE</small>
          </div>
          <nav className="nav-group">
            <div className="nav-label">你的工作區</div>
            <button
              className={`nav-button ${tab === 'overview' ? 'active' : ''}`}
              aria-current={tab === 'overview' ? 'page' : undefined}
              data-testid="nav-overview"
              onClick={() => {
                setTab('overview');
                navigate(null);
              }}
            >
              ◈　機會總覽
            </button>
            <button
              className={`nav-button ${tab === 'stock' ? 'active' : ''}`}
              aria-current={tab === 'stock' ? 'page' : undefined}
              data-testid="nav-stock"
              onClick={() => {
                setTab('stock');
                navigate(symbol ?? 'AAPL');
              }}
            >
              ⌁　股票詳情
            </button>
            <button
              className={`nav-button ${tab === 'research' ? 'active' : ''}`}
              aria-current={tab === 'research' ? 'page' : undefined}
              data-testid="nav-research"
              onClick={() => setTab('research')}
            >
              ◎　研究中心
            </button>
            {['投資組合', '期權研究'].map((name) => (
              <button
                key={name}
                className="nav-button"
                onClick={() => setPlanned(name)}
              >
                {name}
                <small>規劃中</small>
              </button>
            ))}
          </nav>
          <div className="sidebar-foot">
            個人研究工作台
            <br />
            Paper 未啟動
            <br />
            <br />
            先理解，再作決定。
          </div>
        </aside>
        <div className="workspace">
          <header className="topbar">
            <div className="search">
              <span aria-hidden="true">⌕</span>
              <input
                ref={searchRef}
                type="search"
                value={search}
                aria-label="搜尋示範股票"
                placeholder="搜尋股票，例如 AAPL、MSFT…"
                onChange={(event) => {
                  setSearch(event.target.value);
                  if (symbol) {
                    setTab('overview');
                    navigate(null);
                  }
                }}
              />
            </div>
            <div className="top-meta">
              <span className="pill">PAPER · 未啟動</span>
              <button
                className="text-button"
                onClick={() => {
                  setTab('overview');
                  navigate(null);
                }}
              >
                回首頁
              </button>
            </div>
          </header>
          <div className="status-strip" role="status">
            <span>
              {demo
                ? scenario === 'offline'
                  ? '◌ 離線示意 · 舊資料'
                  : '◌ 示範模式 · 無真實連線'
                : session.status === 'paired'
                  ? '◌ 行情已登入 · 連線狀態見股票詳情'
                  : '◌ 行情未登入'}
            </span>
            <span>
              {demo ? '來源：本機人工樣本' : '來源及時間：見個別報價'}
            </span>
            {demo && <span>快照：2026/11/25 21:00 UTC（示例）</span>}
            <strong>即時權益未驗證</strong>
          </div>
          <main>
            <PairingPanel />
            {demo && scenario !== 'sample' && (
              <div className="state-banner" role="status">
                {scenarioMessages[scenario]}
              </div>
            )}
            {tab === 'research' ? (
              <Suspense fallback={<p role="status">載入研究中心…</p>}>
                <ResearchCenter
                  demo={demo}
                  instrumentId={listSelection?.id ?? findCandidate(symbol ?? '')?.id ?? null}
                  symbol={listSelection?.symbol ?? symbol}
                />
              </Suspense>
            ) : symbol && tab === 'stock' ? (
              <Suspense fallback={<p role="status">載入股票工作區…</p>}>
                <StockDetail
                  key={symbol}
                  symbol={symbol}
                  scenario={demo ? scenario : 'sample'}
                  watch={watch}
                  toggleWatch={toggleWatch}
                  navigate={navigate}
                  planned={setPlanned}
                />
              </Suspense>
            ) : !demo ? (
              <Suspense fallback={<p role="status">載入候選工作區…</p>}>
                <CandidateWorkspace key={session.status} paired={session.status === 'paired'} openResearch={(id, selectedSymbol) => {
                  setListSelection({ id, symbol: selectedSymbol });
                  setTab('research');
                }} />
              </Suspense>
            ) : (
              <HomePage
                search={search}
                scenario={demo ? scenario : 'sample'}
                watch={watch}
                toggleWatch={toggleWatch}
                navigate={navigate}
                reset={reset}
                planned={setPlanned}
              />
            )}
            <footer>
              <span>GabFin / 研究示例，非投資建議</span>
              <span>
                {demo
                  ? '沒有連接券商、AI 或交易服務'
                  : '只讀行情 · AI、帳戶及交易未接入'}
              </span>
            </footer>
          </main>
        </div>
      </div>
      <PlannedDialog name={planned} onClose={() => setPlanned(null)} />
    </>
  );
}
