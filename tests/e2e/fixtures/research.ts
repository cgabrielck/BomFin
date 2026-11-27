import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { resolve } from 'node:path';
import { test as base, expect } from '@playwright/test';

/**
 * The research fixture, as the browser sees it.
 *
 * This is a private-stdio harness in the same shape as
 * `secure-market.ts`: one child process, one self-signed TLS origin,
 * and a command channel that never touches an HTTP route. The pairing
 * code travels over the pipe and nowhere else.
 *
 * Two profiles are offered, and both are real:
 *
 * - `configured` serves the whole research chain: real capture over
 *   the fixture's own tape, the real LangGraph runtime, the real
 *   harness verdicts and the real durable store. The only substituted
 *   part is the model provider call, which is answered locally.
 * - `unconfigured` serves a stack with no model and no capture source.
 *   The status route answers `configured: false`, the browser refuses
 *   to start a job, and no report, snapshot or evidence appears. That
 *   is the "an unconfigured stack must not fake a report" case, and it
 *   needs a genuinely unconfigured server rather than a mocked route.
 * - `noHistory` serves a stack whose tape never held the requested
 *   series. The capture refuses the request, so the job fails for a
 *   real reason, and the browser has to show the failure without
 *   inventing a conclusion.
 */
interface ResearchServer {
  origin: string;
  /** True when the stack can run a job. */
  configured: boolean;
  /** The model version the fixture reported. */
  model: string | null;
  command: (
    action: string,
    fields?: Record<string, unknown>,
  ) => Promise<Record<string, unknown>>;
}

export const test = base.extend<{
  research: ResearchServer;
  researchUnconfigured: boolean;
  researchNoHistory: boolean;
}>({
  researchUnconfigured: [false, { option: true }],
  researchNoHistory: [false, { option: true }],
  research: async ({ researchUnconfigured, researchNoHistory }, use) => {
    const env: NodeJS.ProcessEnv = {};
    for (const key of [
      'SystemRoot',
      'SYSTEMROOT',
      'WINDIR',
      'COMSPEC',
      'TEMP',
      'TMP',
    ])
      if (process.env[key]) env[key] = process.env[key];
    env.PYTHONUTF8 = '1';
    env.PYTHON_DOTENV_DISABLED = '1';
    const child = spawn(
      resolve('.venv/Scripts/python.exe'),
      [
        '-I',
        resolve('tests/e2e/fixtures/research-server.py'),
        '--dist',
        resolve('apps/desk-web/dist'),
        '--openssl',
        'C:/Program Files/Git/usr/bin/openssl.exe',
        ...(researchUnconfigured ? ['--unconfigured'] : []),
        ...(researchNoHistory ? ['--no-history'] : []),
      ],
      { env, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true },
    );
    let readyResolve!: (value: {
      origin: string;
      configured: boolean;
      model: string | null;
    }) => void,
      readyReject!: (error: Error) => void;
    const ready = new Promise<{
      origin: string;
      configured: boolean;
      model: string | null;
    }>((yes, no) => {
      readyResolve = yes;
      readyReject = no;
    });
    let counter = 0;
    const pending = new Map<number, (value: Record<string, unknown>) => void>();
    const lines = createInterface({ input: child.stdout });
    lines.on('line', (line) => {
      try {
        const item = JSON.parse(line);
        if (item.kind === 'ready')
          readyResolve({
            origin: String(item.origin),
            configured: item.configured === true,
            model:
              typeof item.model === 'string' ? item.model : null,
          });
        else if (typeof item.id === 'number') {
          pending.get(item.id)?.(item);
          pending.delete(item.id);
        }
      } catch {
        readyReject(new Error('Invalid research fixture response'));
      }
    });
    // Discard diagnostics rather than risk persisting private bootstrap material.
    child.stderr.resume();
    child.once('error', () =>
      readyReject(new Error('Cannot start the research fixture')),
    );
    child.once('exit', () => {
      readyReject(new Error('The research fixture exited'));
      for (const resolve of pending.values()) resolve({ ok: false });
      pending.clear();
    });
    const command = async (
      action: string,
      fields: Record<string, unknown> = {},
    ) => {
      const id = ++counter;
      const answer = new Promise<Record<string, unknown>>((resolve) =>
        pending.set(id, resolve),
      );
      child.stdin.write(JSON.stringify({ id, action, ...fields }) + '\n');
      const timeout = new Promise<never>((_, reject) => {
        const timer = setTimeout(
          () => reject(new Error('Research fixture command timeout')),
          5000,
        );
        timer.unref();
      });
      const value = await Promise.race([answer, timeout]);
      if (value.ok !== true) throw new Error('Research fixture command failed');
      return value;
    };
    try {
      const info = await Promise.race([
        ready,
        new Promise<never>((_, reject) => {
          const timer = setTimeout(
            () => reject(new Error('Research fixture readiness timeout')),
            30000,
          );
          timer.unref();
        }),
      ]);
      await use({ ...info, command });
    } finally {
      if (child.exitCode === null) {
        await command('stop').catch(() => {});
        child.stdin.end();
        await Promise.race([
          new Promise((resolve) => child.once('exit', resolve)),
          new Promise((resolve) => setTimeout(resolve, 6000)),
        ]);
        if (child.exitCode === null) child.kill();
      }
      lines.close();
    }
  },
});

export { expect };
