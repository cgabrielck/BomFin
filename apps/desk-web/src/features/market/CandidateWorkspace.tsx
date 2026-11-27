import { useEffect, useRef, useState } from 'react';
import { fetchCandidates, resolveSymbols } from '../../shared/transport/universe';
import type { CandidateEntry, Resolution } from '../../shared/transport/universe';

export default function CandidateWorkspace({ paired, openResearch }: { paired: boolean; openResearch: (id: string, symbol: string) => void }) {
  const [candidates, setCandidates] = useState<CandidateEntry[]>([]);
  const [symbols, setSymbols] = useState('');
  const [results, setResults] = useState<Resolution[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const active = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!paired) return;
    const controller = new AbortController();
    fetchCandidates(controller.signal).then(setCandidates).catch((reason: Error) => {
      if (!controller.signal.aborted) setError(reason.message);
    });
    return () => { controller.abort(); active.current?.abort(); };
  }, [paired]);
  if (!paired) return <section className="empty"><h1>機會觀察與股票清單</h1><p>請先配對登入，讀取有來源候選與解析股票清單。</p></section>;
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setBusy(true); setError(''); setResults([]);
    try { setResults(await resolveSymbols(symbols, controller.signal)); }
    catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '清單解析失敗'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section aria-label="機會總覽">
    <div className="heading"><div><p className="eyebrow">SOURCED RESEARCH</p><h1>機會觀察與股票清單</h1><p>候選附來源及時間；清單解析不代表投資建議或已完成 AI 研究。</p></div></div>
    {error && <p role="alert">{error}</p>}
    <div className="aside-panel"><h2>分析股票清單</h2>
      <form onSubmit={submit}><label htmlFor="candidate-symbols">美股代號（最多 50 檔，以空格、逗號或換行分隔）</label>
        <textarea id="candidate-symbols" value={symbols} maxLength={8192} onChange={event => setSymbols(event.target.value)} rows={3} />
        <button className="button secondary" disabled={busy || !symbols.trim()}>{busy ? '解析中…' : '解析清單'}</button>
      </form>
      <p className="tiny">線上模式透過 Massive 驗證美股代號；離線模式只讀已登錄標的。研究會使用本地歷史，缺少時按需下載；仍需模型配置。</p>
      <ul>{results.map(row => <li key={row.symbol}><strong>{row.symbol}</strong>{row.name && ` · ${row.name}`} · {row.status === 'resolved' ? '已註冊' : row.status === 'unknown' ? '未知／尚未註冊' : row.status === 'unavailable' ? (row.reason === 'rate_limited' ? '供應商速率限制，請稍後重試' : '供應商暫時不可用') : '代號格式不支援'}{' '}
        {row.status === 'resolved' && row.instrument_id && <button className="text-button" onClick={() => openResearch(row.instrument_id!, row.symbol)}>開啟研究 ↗</button>}
      </li>)}</ul>
    </div>
    <h2>有來源候選 · {candidates.length} 檔</h2>
    {!candidates.length && <div className="empty"><strong>目前沒有有效候選</strong><p>尚未匯入附來源清單，機構自動 feed 未接入。</p></div>}
    <div className="cards">{candidates.map(row => <article className="opportunity" key={row.observation.observation_id}>
      <h3>{row.instrument ? `${row.instrument.symbol} · ${row.instrument.name}` : '標的尚未登錄'}</h3><p>{row.observation.reason}</p>
      {row.instrument && <button className="text-button" onClick={() => openResearch(row.instrument!.instrument_id, row.instrument!.symbol)}>開啟研究 ↗</button>}
      <p>觀測：{row.observation.observed_at} · 到期：{row.observation.expires_at}</p>
      <ul>{row.evidence.map(item => <li key={item.evidence_id}>{item.url && /^https?:\/\//i.test(item.url) ? <a href={item.url} target="_blank" rel="noreferrer">{item.publisher}</a> : item.publisher} · {item.available_at} · {item.license_tag}</li>)}</ul>
    </article>)}</div>
  </section>;
}
