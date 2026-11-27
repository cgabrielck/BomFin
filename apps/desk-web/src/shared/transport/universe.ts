import { csrfNonce } from './research';

export interface Resolution {
  symbol: string;
  status: 'resolved' | 'unknown' | 'invalid' | 'unavailable';
  reason?: string;
  name?: string;
  instrument_id: string | null;
}
export interface CandidateEntry {
  instrument?: { symbol: string; name: string; instrument_id: string } | null;
  observation: { observation_id: string; instrument: string; reason: string; observed_at: string; expires_at: string };
  evidence: { evidence_id: string; publisher: string; url: string | null; available_at: string; license_tag: string }[];
}
async function request(path: string, signal: AbortSignal, symbols?: string) {
  const response = await fetch(path, {
    method: symbols === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', signal,
    headers: symbols === undefined ? {} : { 'Content-Type': 'application/json', 'x-csrf-token': csrfNonce() ?? '' },
    body: symbols === undefined ? undefined : JSON.stringify({ symbols }),
  });
  if (!response.ok) throw new Error(response.status === 401 || response.status === 403
    ? '請重新配對登入' : response.status === 404 ? '候選服務尚未接入' : '清單請求失敗，請檢查輸入或稍後重試');
  return response.json();
}
export async function fetchCandidates(signal: AbortSignal): Promise<CandidateEntry[]> {
  const body = await request('/v1/universe', signal);
  if (!Array.isArray(body.candidates)) throw new Error('候選資料格式錯誤');
  return body.candidates;
}
export async function resolveSymbols(symbols: string, signal: AbortSignal): Promise<Resolution[]> {
  const body = await request('/v1/universe/resolve', signal, symbols);
  if (!Array.isArray(body.results)) throw new Error('清單資料格式錯誤');
  return body.results;
}
