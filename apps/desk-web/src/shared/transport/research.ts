/**
 * The research surface, as the browser sees it.
 *
 * This layer owns the request shape, the response shape and the error
 * shapes for the research endpoints. The components above it must not
 * call `fetch` directly, because the research endpoints fail in ways
 * that mean different things to a reader:
 *
 * - 401 means the session authority refused the request. The session
 *   may be gone, and the desk has to treat that as an expiry rather
 *   than as a research failure.
 * - 400 means the request itself was wrong.
 * - 404 means there is nothing to show: no such job.
 * - 503 means the research plane is not configured or is broken. The
 *   reason travels with it, and the reason is what the reader is shown.
 *
 * The wire types here are local to the browser. They are not the
 * canonical contract: the canonical research schemas live under
 * `schemas/research/` and describe what a role produces, not what a
 * job envelope looks like. This file therefore describes only what the
 * browser needs to read, and it stays tolerant of fields it does not
 * use.
 */

/** The three research roles the harness knows about. */
export type ResearchRole = 'discovery' | 'technical' | 'portfolio';

/** The lifecycle of one research job. */
export type ResearchJobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed';

/** Whether the research plane is configured at all. */
export interface ResearchStatus {
  /** True when a model provider is configured and research can run. */
  configured: boolean;
  /** Why research cannot run, or null when it can. */
  reason: string | null;
}

/** One research job, as the list and the create response describe it. */
export interface ResearchJob {
  job_id: string;
  status: ResearchJobStatus;
  /** The snapshot the conclusion cites, once one exists. */
  snapshot_id: string | null;
  /** The role the job runs, or null for the whole graph. */
  role: ResearchRole | null;
  instrument_id?: string;
  /** The reason a failed job failed, when the backend gives one. */
  reason?: string | null;
}

/** One finding of a role report, with the evidence it cites. */
export interface ResearchFinding {
  text: string;
  evidence_id: string;
}

/** What one role produced. */
export interface ResearchRoleResult {
  role: ResearchRole;
  snapshot_id: string;
  findings?: ResearchFinding[];
  missing_data?: string[];
}

/** What the whole graph produced: one report per role. */
export interface ResearchGraphResult {
  reports?: Record<string, ResearchRoleResult>;
  status?: string;
}

/** One harness verdict about one execution. */
export interface ResearchCheck {
  role?: string;
  execution_result: string;
  reasons?: string[];
  model_version?: string;
  prompt_version?: number;
  checked_at?: string;
  snapshot_id?: string;
}

/** The metadata a snapshot carries, when the backend exposes it. */
export interface ResearchSnapshotMeta {
  snapshot_id: string;
  as_of?: string;
  data_quality?: string[];
}

/** One job with everything the browser needs to show it. */
export interface ResearchJobDetail extends ResearchJob {
  /** The role result, or the graph object when the whole graph ran. */
  result?: ResearchRoleResult | ResearchGraphResult | null;
  /** The harness verdicts for this job. */
  checks?: ResearchCheck[];
  /** The snapshot metadata, when the backend exposes it. */
  snapshot?: ResearchSnapshotMeta | null;
}

/** The session is gone; the desk has to treat this as an expiry. */
export class ResearchSessionRequired extends Error {
  readonly status = 401;
  constructor(message = '登入已過期') {
    super(message);
    this.name = 'ResearchSessionRequired';
  }
}

/** The request was not acceptable. */
export class ResearchInvalid extends Error {
  readonly status = 400;
  constructor(message: string) {
    super(message);
    this.name = 'ResearchInvalid';
  }
}

/** There is no such job. */
export class ResearchMissing extends Error {
  readonly status = 404;
  constructor(message = '找不到這個研究工作') {
    super(message);
    this.name = 'ResearchMissing';
  }
}

/**
 * The research plane cannot answer right now.
 *
 * This is the state that matters most: a research plane with no model
 * configured must say so rather than return a report. The reason
 * travels with the failure so the reader learns what is missing.
 */
export class ResearchUnavailable extends Error {
  readonly status: number;
  constructor(message: string, status = 503) {
    super(message);
    this.name = 'ResearchUnavailable';
    this.status = status;
  }
}

/** The largest response the browser will read, in bytes. */
const MAX_BODY_BYTES = 1048576;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function textOf(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

/** Read the reason the backend gave, without leaking anything else. */
async function detailOf(response: Response): Promise<string | null> {
  const text = await response.text();
  if (text.length > MAX_BODY_BYTES) return null;
  try {
    const body: unknown = JSON.parse(text);
    if (isRecord(body)) return textOf(body.detail) ?? textOf(body.reason);
  } catch {
    /* A body that is not JSON carries no detail worth showing. */
  }
  return null;
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text.length > MAX_BODY_BYTES)
    throw new ResearchUnavailable('研究資料過大', 503);
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new ResearchUnavailable('研究回應格式無法解析', 503);
  }
}

/** The CSRF nonce the server issued with the session. */
export function csrfNonce(): string | null {
  const value = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith('__Host-gabfin_csrf='));
  try {
    return value
      ? decodeURIComponent(value.slice(value.indexOf('=') + 1))
      : null;
  } catch {
    return null;
  }
}

async function guard(response: Response): Promise<void> {
  if (response.status === 401)
    throw new ResearchSessionRequired('研究請求被拒絕（登入狀態可能已失效）');
  if (response.status === 400)
    throw new ResearchInvalid((await detailOf(response)) ?? '研究請求不被接受');
  if (response.status === 404) throw new ResearchMissing();
  if (response.status === 503) {
    const detail = await detailOf(response);
    throw new ResearchUnavailable(detail ?? '研究服務尚未設定或暫時不可用', 503);
  }
  if (!response.ok)
    throw new ResearchUnavailable('研究服務暫時不可用', response.status);
}

/** Read the research plane's own readiness. */
export async function fetchResearchStatus(
  signal?: AbortSignal,
): Promise<ResearchStatus> {
  const response = await fetch('/v1/research/status', {
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
    headers: { Accept: 'application/json' },
  });
  await guard(response);
  const body = await readJson(response);
  if (!isRecord(body))
    throw new ResearchUnavailable('研究狀態格式無法解析', 503);
  return {
    configured: body.configured === true,
    reason: textOf(body.reason),
  };
}

/** Read the jobs this session already owns. */
export async function fetchResearchJobs(
  signal?: AbortSignal,
): Promise<ResearchJob[]> {
  const response = await fetch('/v1/research/jobs', {
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
    headers: { Accept: 'application/json' },
  });
  await guard(response);
  const body = await readJson(response);
  if (!isRecord(body) || !Array.isArray(body.jobs))
    throw new ResearchUnavailable('研究工作清單格式無法解析', 503);
  return body.jobs.filter(isRecord).map(parseJob);
}

function parseRole(value: unknown): ResearchRole | null {
  return value === 'discovery' ||
    value === 'technical' ||
    value === 'portfolio'
    ? value
    : null;
}

function parseStatus(value: unknown): ResearchJobStatus {
  return value === 'queued' ||
    value === 'running' ||
    value === 'completed' ||
    value === 'failed'
    ? value
    : 'queued';
}

function parseJob(value: Record<string, unknown>): ResearchJob {
  return {
    job_id: textOf(value.job_id) ?? '',
    status: parseStatus(value.status),
    snapshot_id: textOf(value.snapshot_id),
    role: parseRole(value.role),
    instrument_id: textOf(value.instrument_id) ?? undefined,
    reason: textOf(value.reason),
  };
}

/**
 * Ask the desk to start one research job.
 *
 * The role is sent as it is: null means the whole graph, which is what
 * the backend runs when no single role is named.
 */
export async function createResearchJob(
  instrumentId: string,
  role: ResearchRole | null,
  signal?: AbortSignal,
): Promise<ResearchJob> {
  const nonce = csrfNonce();
  if (!nonce) throw new ResearchSessionRequired('請重新配對登入');
  const response = await fetch('/v1/research/jobs', {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    signal,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'X-CSRF-Token': nonce,
    },
    body: JSON.stringify({ instrument_id: instrumentId, role }),
  });
  await guard(response);
  const body = await readJson(response);
  if (!isRecord(body))
    throw new ResearchUnavailable('研究工作格式無法解析', 503);
  return parseJob(body);
}

/** Read one job, including its result, checks and snapshot metadata. */
export async function fetchResearchJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<ResearchJobDetail> {
  const response = await fetch(
    `/v1/research/jobs/${encodeURIComponent(jobId)}`,
    {
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
      headers: { Accept: 'application/json' },
    },
  );
  await guard(response);
  const body = await readJson(response);
  if (!isRecord(body))
    throw new ResearchUnavailable('研究工作格式無法解析', 503);
  const job = parseJob(body);
  return {
    ...job,
    result: isRecord(body.result)
      ? (body.result as ResearchJobDetail['result'])
      : null,
    checks: Array.isArray(body.checks)
      ? body.checks.filter(isRecord).map((check) => ({
          role: textOf(check.role) ?? undefined,
          execution_result: textOf(check.execution_result) ?? 'unknown',
          reasons: Array.isArray(check.reasons)
            ? check.reasons.filter((item): item is string => typeof item === 'string')
            : undefined,
          model_version: textOf(check.model_version) ?? undefined,
          prompt_version:
            typeof check.prompt_version === 'number'
              ? check.prompt_version
              : undefined,
          checked_at: textOf(check.checked_at) ?? undefined,
          snapshot_id: textOf(check.snapshot_id) ?? undefined,
        }))
      : undefined,
    snapshot: isRecord(body.snapshot)
      ? {
          snapshot_id: textOf(body.snapshot.snapshot_id) ?? '',
          as_of: textOf(body.snapshot.as_of) ?? undefined,
          data_quality: Array.isArray(body.snapshot.data_quality)
            ? body.snapshot.data_quality.filter(
                (item): item is string => typeof item === 'string',
              )
            : undefined,
        }
      : null,
  };
}
