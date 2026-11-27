import { useEffect, useState } from 'react';
import {
  AnalysisInvalid,
  AnalysisMissing,
  AnalysisRefused,
  AnalysisUnavailable,
} from '../../shared/transport/analysis';

/**
 * The state one analysis surface can be in.
 *
 * The states are kept apart because they mean different things to a
 * reader: nothing yet, nothing to show, a broken service, a refused
 * request, or a request this browser should not make. Collapsing them
 * into "error" is what makes a UI lie.
 */
export type AnalysisState<T> =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'ready'; data: T }
  | { phase: 'missing'; message: string }
  | { phase: 'unavailable'; message: string }
  | { phase: 'invalid'; message: string }
  | { phase: 'refused'; message: string };

export interface AnalysisView<T> {
  state: AnalysisState<T>;
  /** True while a request is in flight, including the first one. */
  loading: boolean;
}

/**
 * Run one analysis request whenever its key changes.
 *
 * A request that is still in flight when the key changes is abandoned:
 * its result belongs to a different question and must not be shown as
 * the answer to this one. The same rule the market reader already
 * follows for a different instrument.
 */
export function useAnalysis<T>(
  key: string | null,
  load: () => Promise<T>,
): AnalysisView<T> {
  const [state, setState] = useState<AnalysisState<T>>({ phase: 'idle' });
  useEffect(() => {
    if (key === null) {
      setState({ phase: 'idle' });
      return;
    }
    let current = true;
    setState({ phase: 'loading' });
    load().then(
      (data) => {
        if (current) setState({ phase: 'ready', data });
      },
      (error: unknown) => {
        if (!current) return;
        if (error instanceof AnalysisRefused)
          setState({ phase: 'refused', message: error.message });
        else if (error instanceof AnalysisMissing)
          setState({ phase: 'missing', message: error.message });
        else if (error instanceof AnalysisInvalid)
          setState({ phase: 'invalid', message: error.message });
        else if (error instanceof AnalysisUnavailable)
          setState({ phase: 'unavailable', message: error.message });
        else
          setState({
            phase: 'unavailable',
            message: '分析服務暫時不可用',
          });
      },
    );
    return () => {
      current = false;
    };
    // `load` is rebuilt every render; the key is what identifies the
    // question, and re-running on every render would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return { state, loading: state.phase === 'loading' };
}
