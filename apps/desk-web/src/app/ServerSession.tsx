import { createContext, useContext, useEffect, useRef, useState } from 'react';
import type { PropsWithChildren } from 'react';

type Status = 'checking' | 'paired' | 'needs_pair';
interface Session {
  mode: 'demo' | 'server';
  status: Status;
  problem: string;
  setMode: (mode: 'demo' | 'server') => void;
  pair: (code: string) => Promise<void>;
  logout: () => Promise<void>;
  expire: () => void;
}
const Context = createContext<Session | null>(null);
function noncePresent() {
  return document.cookie
    .split('; ')
    .some((value) => value.startsWith('__Host-gabfin_csrf='));
}

export function ServerSession({ children }: PropsWithChildren) {
  const [mode, setModeState] = useState<'demo' | 'server'>('demo');
  const [status, setStatus] = useState<Status>('needs_pair');
  const [problem, setProblem] = useState('');
  const generation = useRef(0);
  const setMode = (value: 'demo' | 'server') => {
    if (value === 'server' && location.protocol !== 'https:') {
      setProblem('伺服器行情需要同源 HTTPS；目前保留示範模式。');
      return;
    }
    generation.current++;
    setProblem('');
    setModeState(value);
    setStatus(value === 'server' ? 'checking' : 'needs_pair');
  };
  useEffect(() => {
    if (mode !== 'server') return;
    const controller = new AbortController(),
      current = ++generation.current;
    fetch('/session', {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    })
      .then((response) => {
        if (current === generation.current)
          setStatus(response.ok && noncePresent() ? 'paired' : 'needs_pair');
      })
      .catch(() => {
        if (!controller.signal.aborted && current === generation.current) {
          setProblem('無法核對登入狀態');
          setStatus('needs_pair');
        }
      });
    return () => {
      generation.current++;
      controller.abort();
    };
  }, [mode]);
  const pair = async (code: string) => {
    const current = ++generation.current;
    setStatus('checking');
    setProblem('');
    try {
      const response = await fetch('/pair', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      });
      if (!response.ok || !noncePresent())
        throw new Error('配對碼無效、過期或伺服器未就緒');
      if (current === generation.current) setStatus('paired');
    } catch (error) {
      if (current === generation.current) {
        setStatus('needs_pair');
        setProblem(error instanceof Error ? error.message : '配對失敗');
      }
    }
  };
  const expire = () => {
    generation.current++;
    setStatus('needs_pair');
    setProblem('登入已失效，行情畫面已清除，請重新配對。');
  };
  const logout = async () => {
    const current = ++generation.current;
    setStatus('needs_pair');
    setProblem('正在向伺服器確認登出…');
    try {
      const nonce = document.cookie
        .split('; ')
        .find((value) => value.startsWith('__Host-gabfin_csrf='))
        ?.split('=')
        .slice(1)
        .join('=');
      const response = await fetch('/logout', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { 'X-CSRF-Token': nonce ? decodeURIComponent(nonce) : '' },
      });
      if (current === generation.current)
        setProblem(
          response.ok || response.status === 401
            ? ''
            : '伺服器登出未確認；已清除畫面，請稍後重試。',
        );
    } catch {
      if (current === generation.current)
        setProblem('伺服器登出未確認；已清除畫面，請稍後重試。');
    }
  };
  return (
    <Context.Provider
      value={{ mode, status, problem, setMode, pair, logout, expire }}
    >
      {children}
    </Context.Provider>
  );
}

export function useServerSession() {
  const value = useContext(Context);
  if (!value) throw new Error('Session provider required');
  return value;
}

export function SourceControl() {
  const session = useServerSession();
  return (
    <>
      <label htmlFor="source-mode">資料模式</label>
      <select
        id="source-mode"
        aria-label="資料模式"
        value={session.mode}
        onChange={(event) =>
          session.setMode(event.target.value as 'demo' | 'server')
        }
      >
        <option value="demo">示範資料</option>
        <option value="server">伺服器行情</option>
      </select>
      {session.mode === 'server' && session.status === 'paired' && (
        <button onClick={() => void session.logout()}>登出</button>
      )}
    </>
  );
}

export function PairingPanel() {
  const session = useServerSession();
  const [code, setCode] = useState('');
  if (session.mode !== 'server')
    return session.problem ? (
      <div role="status" className="state-banner">
        {session.problem}
      </div>
    ) : null;
  if (session.status === 'paired') return null;
  return (
    <section className="aside-panel" aria-label="配對登入">
      <h2>登入行情工作台</h2>
      <p className="tiny">
        輸入本機主機提供的短效單次配對碼；不用券商帳號或密碼。行情尚未登入，價格保持空白。
      </p>
      <form
        className="pairing-form"
        onSubmit={(event) => {
          event.preventDefault();
          const value = code;
          setCode('');
          void session.pair(value);
        }}
      >
        <label htmlFor="pair-code">配對碼</label>
        <input
          id="pair-code"
          type="password"
          autoComplete="off"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          disabled={session.status === 'checking'}
        />
        <button
          className="button"
          disabled={!code || session.status === 'checking'}
        >
          配對登入
        </button>
      </form>
      {session.status === 'checking' && <p role="status">核對登入狀態…</p>}
      {session.problem && <p role="alert">{session.problem}</p>}
    </section>
  );
}
