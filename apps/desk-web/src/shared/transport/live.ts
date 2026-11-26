import type { MarketSnapshot, SubscriptionKey } from '../contracts/generated';
import { parseFrame, parseSnapshot } from '../contracts/validate-market';
import type { BrowserMarketFrame } from '../contracts/validate-market';

export class SessionRequired extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SessionRequired';
  }
}
export type StreamStatus =
  | 'connecting'
  | 'connected'
  | 'recovering'
  | 'disconnected'
  | 'unauthorized'
  | 'error';
export function csrfNonce() {
  const value = document.cookie
    .split('; ')
    .find((value) => value.startsWith('__Host-gabfin_csrf='));
  try {
    return value
      ? decodeURIComponent(value.slice(value.indexOf('=') + 1))
      : null;
  } catch {
    return null;
  }
}

export async function fetchSnapshot(
  keys: SubscriptionKey[],
  signal: AbortSignal,
): Promise<MarketSnapshot> {
  if (location.protocol !== 'https:') throw new Error('行情模式需要同源 HTTPS');
  const csrf = csrfNonce();
  if (!csrf) throw new SessionRequired('請重新配對登入');
  const response = await fetch('/market/snapshot', {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: JSON.stringify({ version: 1, keys }),
  });
  if (response.status === 401) throw new SessionRequired('登入已過期');
  if (response.status === 403) throw new Error('此股票未獲授權或未接入');
  if (!response.ok) throw new Error('行情服務暫時不可用');
  const text = await response.text();
  if (text.length > 1048576) throw new Error('行情資料過大');
  return parseSnapshot(JSON.parse(text), keys);
}

export function subscribeMarket(
  keys: SubscriptionKey[],
  onFrame: (frame: BrowserMarketFrame) => void,
  signal: AbortSignal,
  onStatus: (state: StreamStatus) => void,
) {
  let socket: WebSocket | undefined,
    timer: ReturnType<typeof setTimeout> | undefined,
    stopped = false,
    attempts = 0;
  const open = () => {
    if (stopped || signal.aborted) return;
    onStatus(attempts ? 'recovering' : 'connecting');
    let position: { epoch: string; cursor: number } | undefined;
    socket = new WebSocket(
      new URL('/market/stream', location.origin.replace('https:', 'wss:')),
    );
    socket.onopen = () => socket?.send(JSON.stringify({ version: 1, keys }));
    socket.onmessage = (event) => {
      try {
        if (typeof event.data !== 'string' || event.data.length > 1048576)
          throw new Error('行情訊息過大');
        const frame = parseFrame(JSON.parse(event.data), keys);
        if (frame.kind === 'error') {
          onStatus('recovering');
          socket?.close();
          return;
        }
        if (frame.kind === 'snapshot') {
          if (position) throw new Error('重複快照');
          position = {
            epoch: frame.payload.epoch,
            cursor: frame.payload.cursor,
          };
        } else {
          if (
            !position ||
            frame.payload.epoch !== position.epoch ||
            frame.payload.sequence !== position.cursor + 1
          ) {
            onStatus('recovering');
            socket?.close();
            return;
          }
          position.cursor = frame.payload.sequence;
        }
        onFrame(frame);
        onStatus('connected');
      } catch {
        onStatus('error');
        socket?.close();
      }
    };
    socket.onclose = async (event) => {
      if (stopped || signal.aborted) return;
      if (event.code === 1008) {
        onStatus('unauthorized');
        return;
      }
      onStatus('disconnected');
      // Proxies and a racing upstream expiry can hide the policy close code.
      // The session authority decides expiry, not the transport's error number.
      try {
        const response = await fetch('/session', {
          credentials: 'same-origin',
          cache: 'no-store',
          signal: AbortSignal.any([signal, AbortSignal.timeout(2000)]),
        });
        if (stopped || signal.aborted) return;
        if (response.status === 401) {
          stopped = true;
          onStatus('unauthorized');
          return;
        }
      } catch {
        if (stopped || signal.aborted) return;
      }
      if (attempts < 3) {
        timer = setTimeout(open, 250 * 2 ** attempts);
        attempts++;
      }
    };
    socket.onerror = () => onStatus('disconnected');
  };
  const close = () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    socket?.close();
    signal.removeEventListener('abort', close);
  };
  signal.addEventListener('abort', close, { once: true });
  open();
  return close;
}
