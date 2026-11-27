import type {
  CapabilitiesResponse,
  IndicatorResponse,
  MacroResponse,
} from '../contracts/generated';

/**
 * The three read-only analysis surfaces.
 *
 * This layer owns the request shape and the error shapes. The components
 * above it must not call `fetch` directly: the analysis endpoints fail in
 * five distinguishable ways, and "the request failed" is not a message a
 * user can act on.
 *
 * The failures that mean different things:
 *
 * - 400 means the request itself was wrong.
 * - 401 means the request was refused. The session authority decides
 *   whether a session is gone, not this layer, so the refusal is
 *   reported as a refusal.
 * - 403 means the session is valid but lacks the capability.
 * - 404 means there is nothing to show: the instrument has no stored
 *   series, or the series is not one the contract accepts.
 * - 503 means the plane is broken. Showing the last value as if it were
 *   current would be a lie, so the error is passed through instead.
 */

/** The analysis surface could not answer right now. */
export class AnalysisUnavailable extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'AnalysisUnavailable';
    this.status = status;
  }
}

/** The request itself was not acceptable. */
export class AnalysisInvalid extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AnalysisInvalid';
  }
}

/** There is no stored series to show. */
export class AnalysisMissing extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AnalysisMissing';
  }
}

/**
 * The request was refused.
 *
 * A browser cannot send the `Origin` header the session guard requires,
 * so an analysis GET made from the desk is refused even with a valid
 * session. That is a backend limitation, not a logout: the market view
 * keeps working and this error says only that the analysis surface is
 * out of reach.
 */
export class AnalysisRefused extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'AnalysisRefused';
    this.status = status;
  }
}

const MISSING: Record<string, string> = {
  '/v1/indicators': '此標的尚無可計算的歷史序列',
  '/v1/macro': '此宏觀序列尚無已發布的觀測值',
  '/v1/capabilities': '尚無已量測的行情來源',
};

const UNAVAILABLE: Record<string, string> = {
  '/v1/indicators': '指標服務暫時不可用',
  '/v1/macro': '宏觀服務暫時不可用',
  '/v1/capabilities': '來源能力服務暫時不可用',
};

async function detailOf(response: Response): Promise<string> {
  const text = await response.text();
  if (text.length > 1048576) return '分析資料過大';
  try {
    const body: unknown = JSON.parse(text);
    if (body && typeof body === 'object' && 'detail' in body)
      return String((body as { detail: unknown }).detail);
  } catch {
    /* A body that is not JSON carries no detail worth showing. */
  }
  return '請求參數不被接受';
}

async function get<T>(
  path: string,
  query: URLSearchParams,
): Promise<T> {
  const search = query.toString();
  const response = await fetch(search ? `${path}?${search}` : path, {
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  if (response.status === 401)
    throw new AnalysisRefused('分析請求被拒絕（工作台未送出有效的 Origin 標頭）', 401);
  if (response.status === 403)
    throw new AnalysisUnavailable('此身分沒有行情讀取權限', 403);
  if (response.status === 404)
    throw new AnalysisMissing(MISSING[path] ?? '找不到該資料');
  if (response.status === 400)
    throw new AnalysisInvalid(await detailOf(response));
  if (response.status === 503)
    throw new AnalysisUnavailable(UNAVAILABLE[path] ?? '分析服務暫時不可用', 503);
  if (!response.ok)
    throw new AnalysisUnavailable(UNAVAILABLE[path] ?? '分析服務暫時不可用', response.status);
  const text = await response.text();
  if (text.length > 1048576)
    throw new AnalysisUnavailable('分析資料過大', 503);
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new AnalysisUnavailable('分析回應格式無法解析', 503);
  }
}

/** The indicators computed from the stored history of one instrument. */
export async function fetchIndicators(
  instrumentId: string,
  timeframe: string,
  indicators?: string[],
  limit?: number,
): Promise<IndicatorResponse> {
  const query = new URLSearchParams();
  query.set('instrument_id', instrumentId);
  query.set('timeframe', timeframe);
  for (const name of indicators ?? []) query.append('indicator', name);
  if (limit !== undefined) query.set('limit', String(limit));
  return get<IndicatorResponse>('/v1/indicators', query);
}

/** The macro observations that had been released by `asOf`. */
export async function fetchMacro(
  seriesId?: string,
  asOf?: string,
): Promise<MacroResponse> {
  const query = new URLSearchParams();
  if (seriesId) query.set('series_id', seriesId);
  if (asOf) query.set('as_of', asOf);
  return get<MacroResponse>('/v1/macro', query);
}

/** What each measured feed can actually do. */
export async function fetchCapabilities(): Promise<CapabilitiesResponse> {
  return get<CapabilitiesResponse>('/v1/capabilities', new URLSearchParams());
}
