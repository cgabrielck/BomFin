import { useState } from 'react';
import { candidates } from './demo-catalog';
import type { Scenario } from './demo-catalog';
import { AccountSummary } from './AccountSummary';

interface Props {
  search: string;
  scenario: Scenario;
  watch: Set<string>;
  toggleWatch: (s: string) => void;
  navigate: (s: string | null) => void;
  reset: () => void;
  planned: (name: string) => void;
}
export default function HomePage({
  search,
  scenario,
  watch,
  toggleWatch,
  navigate,
  reset,
  planned,
}: Props) {
  const [filter, setFilter] = useState<'all' | 'watch'>('all');
  const query = search.trim().toLowerCase();
  const visible =
    scenario === 'empty'
      ? []
      : candidates.filter(
          (item) =>
            (filter === 'all' || watch.has(item.symbol)) &&
            `${item.symbol} ${item.name}`.toLowerCase().includes(query),
        );
  return (
    <section aria-label="機會總覽">
      <div className="heading">
        <div>
          <p className="eyebrow">YOUR MARKET BRIEF</p>
          <h1>值得留意的下一步。</h1>
          <p>先看風險，再探索機會。每個觀點都應有證據。</p>
        </div>
        <button className="button secondary" onClick={() => planned('分析股票清單')}>
          ＋ 分析清單
        </button>
      </div>
      <div className="notice">
        <span className="notice-icon" aria-hidden="true">
          ◷
        </span>
        <div>
          <strong>持倉風險區 · 尚未連接帳戶</strong>
          <p>正式持倉的重要變化會置頂；目前沒有持倉或風險判斷。</p>
        </div>
        <button className="text-button" onClick={() => planned('持倉風險摘要')}>
          了解設計 ↗
        </button>
      </div>
      <div className="metrics">
        <div className="metric">
          <div className="label">候選 · 設計示例</div>
          <div className="number">
            {visible.length.toString().padStart(2, '0')} <small>檔</small>
          </div>
          <div className="foot">非買入排名</div>
        </div>
        <div className="metric">
          <div className="label">研究服務</div>
          <div className="number">—</div>
          <div className="foot">未接入，不假裝已完成</div>
        </div>
        <div className="metric">
          <div className="label">自選 · 本頁暫存</div>
          <div className="number">
            {watch.size} <small>檔</small>
          </div>
          <div className="foot">不啟動交易</div>
        </div>
      </div>
      <div className="home-grid">
        <div>
          <div className="section-title">
            <h2>機會觀察</h2>
            <small>人工示例，非投資建議</small>
          </div>
          <div className="filters" aria-label="候選篩選">
            {(['all', 'watch'] as const).map((value) => (
              <button
                key={value}
                className={`filter ${value === filter ? 'active' : ''}`}
                aria-pressed={value === filter}
                onClick={() => setFilter(value)}
              >
                {value === 'all' ? '全部候選' : '我的自選'}
              </button>
            ))}
          </div>
          <div className="result-count">{visible.length} 檔示範股票 · 未接入動態機會池</div>
          <div className="cards">
            {visible.map((item) => (
              <article key={item.id} className="opportunity">
                <div className="card-top">
                  <div className="ticker-icon" aria-hidden="true">
                    {item.symbol[0]}
                  </div>
                  <div>
                    <button className="card-title" onClick={() => navigate(item.symbol)}>
                      {item.symbol} ↗
                    </button>
                    <div className="stock-name">{item.name} · 美股示例</div>
                  </div>
                  <span className="pill amber">{item.tag} · 示例</span>
                </div>
                <p className="why">{item.why}</p>
                <div className="card-foot">
                  <span>{item.horizon}</span>
                  <span>{item.missing}</span>
                  <button
                    className="text-button"
                    aria-label={`${item.symbol} ${watch.has(item.symbol) ? '移出' : '加入'}自選`}
                    aria-pressed={watch.has(item.symbol)}
                    onClick={() => toggleWatch(item.symbol)}
                  >
                    {watch.has(item.symbol) ? '✓ 已加入自選' : '＋ 自選'}
                  </button>
                </div>
              </article>
            ))}
          </div>
          {!visible.length && (
            <div className="empty">
              <strong>目前沒有符合的股票</strong>
              <p>可試 AAPL、MSFT 或 NVDA；本頁只有三檔固定示例。</p>
              <button
                className="button secondary"
                onClick={() => {
                  setFilter('all');
                  reset();
                }}
              >
                重設篩選
              </button>
            </div>
          )}
        </div>
        <aside className="home-aside">
          <AccountSummary />
          <div className="aside-panel">
            <h3>研究工作區</h3>
            <span className="pill amber">未執行 AI</span>
            <p className="tiny">
              支持證據、反證、時間尺度與資料缺口會分開呈現；沒有足夠優勢也是有效結果。
            </p>
            <button className="text-button" onClick={() => planned('研究中心')}>
              查看規劃 ↗
            </button>
          </div>
        </aside>
      </div>
    </section>
  );
}
