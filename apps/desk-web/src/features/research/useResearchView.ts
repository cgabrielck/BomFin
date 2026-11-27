import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ResearchInvalid,
  ResearchMissing,
  ResearchSessionRequired,
  ResearchUnavailable,
  createResearchJob,
  fetchResearchJob,
  fetchResearchJobs,
  fetchResearchStatus,
} from '../../shared/transport/research';
import type {
  ResearchJob,
  ResearchJobDetail,
  ResearchJobStatus,
  ResearchRole,
  ResearchStatus,
} from '../../shared/transport/research';

/**
 * The research job lifecycle, as the browser reads it.
 *
 * The phases are kept apart because they mean different things to a
 * reader: nothing has been asked yet, the plane is not configured, a
 * job is running, a job failed, or a request was refused. Collapsing
 * them into "error" is what makes a research UI lie.
 */
export type ResearchPhase =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'unconfigured'; reason: string | null }
  | { phase: 'ready'; status: ResearchStatus }
  | { phase: 'refused'; message: string }
  | { phase: 'unavailable'; message: string };

/** How often a running job is asked about itself. */
const POLL_INTERVAL_MS = 1500;

/** How long a job may stay running before the browser stops watching. */
const POLL_DEADLINE_MS = 120000;

export interface ResearchView {
  phase: ResearchPhase;
  /** True while the first read of the plane is in flight. */
  loading: boolean;
  /** The jobs this session owns, newest first. */
  jobs: ResearchJob[];
  /** The job currently being watched, with its result. */
  active: ResearchJobDetail | null;
  /** True while a job is being created. */
  submitting: boolean;
  /** The reason the last attempt failed, if it failed. */
  problem: string | null;
  /** Ask the desk to start a job. */
  start: (instrumentId: string, role: ResearchRole | null) => Promise<void>;
  /** Watch one job instead of the newest. */
  watch: (jobId: string) => void;
  /** Stop watching and clear the active job. */
  reset: () => void;
}

/**
 * Read the research plane and watch the job it is running.
 *
 * Two rules shape this hook.
 *
 * The first is that a request which is still in flight when the
 * question changes is abandoned. Its answer belongs to a different
 * question, and showing it as the answer to this one is how a research
 * panel ends up describing the wrong instrument.
 *
 * The second is that polling stops when the component unmounts, when
 * the instrument changes, and when the session goes away. A poll that
 * outlives its question can deliver an old report into a new window.
 */
export function useResearchView(
  enabled: boolean,
  instrumentId: string | null,
  onSessionRequired: () => void,
): ResearchView {
  const [phase, setPhase] = useState<ResearchPhase>({ phase: 'idle' });
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [active, setActive] = useState<ResearchJobDetail | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [watched, setWatched] = useState<string | null>(null);
  const generation = useRef(0);
  const expire = useRef(onSessionRequired);
  expire.current = onSessionRequired;

  // The plane's own readiness, and the jobs this session already owns.
  useEffect(() => {
    if (!enabled) {
      setPhase({ phase: 'idle' });
      setJobs([]);
      setActive(null);
      setWatched(null);
      setProblem(null);
      return;
    }
    const controller = new AbortController();
    const current = ++generation.current;
    setPhase({ phase: 'loading' });
    void Promise.all([
      fetchResearchStatus(controller.signal),
      fetchResearchJobs(controller.signal).catch(() => [] as ResearchJob[]),
    ]).then(
      ([status, listed]) => {
        if (current !== generation.current || controller.signal.aborted) return;
        setJobs(listed);
        setPhase(
          status.configured
            ? { phase: 'ready', status }
            : { phase: 'unconfigured', reason: status.reason },
        );
      },
      (error: unknown) => {
        if (current !== generation.current || controller.signal.aborted) return;
        setPhase(refusal(error, expire.current));
      },
    );
    return () => {
      generation.current++;
      controller.abort();
    };
  }, [enabled]);

  // The instrument changes: the jobs on screen belong to the previous
  // instrument, so they are cleared rather than relabelled.
  useEffect(() => {
    setActive(null);
    setWatched(null);
    setProblem(null);
  }, [instrumentId]);

  // The job being watched is polled until it settles. The poll is
  // abandoned when the question changes or the session goes away.
  useEffect(() => {
    if (!watched || !enabled) return;
    const controller = new AbortController();
    const current = ++generation.current;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    const started = Date.now();

    const poll = async () => {
      try {
        const detail = await fetchResearchJob(watched, controller.signal);
        if (stopped || current !== generation.current) return;
        setActive(detail);
        setJobs((previous) =>
          previous.map((job) =>
            job.job_id === detail.job_id
              ? {
                  ...job,
                  status: detail.status,
                  snapshot_id: detail.snapshot_id,
                }
              : job,
          ),
        );
        if (
          detail.status === 'queued' ||
          detail.status === 'running'
        ) {
          if (Date.now() - started > POLL_DEADLINE_MS) {
            setProblem('研究工作仍在進行，但已停止自動更新；請重新整理。');
            return;
          }
          timer = setTimeout(() => void poll(), POLL_INTERVAL_MS);
          return;
        }
      } catch (error) {
        if (stopped || current !== generation.current) return;
        if (error instanceof ResearchSessionRequired) {
          expire.current();
          return;
        }
        setProblem(
          error instanceof ResearchUnavailable
            ? error.message
            : error instanceof ResearchMissing
              ? '研究工作已不存在'
              : error instanceof ResearchInvalid
                ? error.message
                : '研究工作無法讀取',
        );
      }
    };
    void poll();
    return () => {
      stopped = true;
      generation.current++;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [watched, enabled, expire]);

  const start = useCallback(
    async (target: string, role: ResearchRole | null) => {
      const current = ++generation.current;
      setSubmitting(true);
      setProblem(null);
      try {
        const job = await createResearchJob(target, role);
        if (current !== generation.current) return;
        setJobs((previous) => [job, ...previous]);
        setWatched(job.job_id);
        setPhase((previous) =>
          previous.phase === 'unconfigured'
            ? { phase: 'unconfigured', reason: previous.reason }
            : previous,
        );
      } catch (error) {
        if (current !== generation.current) return;
        if (error instanceof ResearchSessionRequired) {
          expire.current();
          return;
        }
        if (error instanceof ResearchUnavailable) setProblem(error.message);
        else if (error instanceof ResearchInvalid) setProblem(error.message);
        else setProblem('研究工作無法建立');
      } finally {
        if (current === generation.current) setSubmitting(false);
      }
    },
    [expire],
  );

  const watch = useCallback((jobId: string) => {
    setWatched(jobId);
    setProblem(null);
  }, []);

  const reset = useCallback(() => {
    setWatched(null);
    setActive(null);
    setProblem(null);
  }, []);

  return {
    phase,
    loading: phase.phase === 'loading',
    jobs,
    active,
    submitting,
    problem,
    start,
    watch,
    reset,
  };
}

/**
 * Turn a failure into a phase.
 *
 * A refusal is not a research failure: the session authority decided
 * it, so the desk treats it as an expiry and the reader is told the
 * session may be gone.
 */
function refusal(
  error: unknown,
  onSessionRequired: () => void,
): ResearchPhase {
  if (error instanceof ResearchSessionRequired) {
    onSessionRequired();
    return { phase: 'refused', message: error.message };
  }
  if (error instanceof ResearchUnavailable)
    return { phase: 'unavailable', message: error.message };
  if (error instanceof ResearchMissing)
    return { phase: 'unavailable', message: '研究工作不存在' };
  if (error instanceof ResearchInvalid)
    return { phase: 'unavailable', message: error.message };
  return { phase: 'unavailable', message: '研究服務暫時不可用' };
}

/** The label a job status reads as. */
export function statusLabel(status: ResearchJobStatus): string {
  switch (status) {
    case 'queued':
      return '排隊中';
    case 'running':
      return '執行中';
    case 'completed':
      return '已完成';
    case 'failed':
      return '失敗';
  }
}

/** The label a role reads as. */
export function roleLabel(role: ResearchRole | null): string {
  switch (role) {
    case 'discovery':
      return '探索';
    case 'technical':
      return '技術';
    case 'portfolio':
      return '投資組合';
    default:
      return '全流程';
  }
}
