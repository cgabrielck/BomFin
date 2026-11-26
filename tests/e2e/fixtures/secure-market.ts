import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { resolve } from 'node:path';
import { test as base, expect } from '@playwright/test';

interface Server {
  origin: string;
  command: (
    action: string,
    fields?: Record<string, unknown>,
  ) => Promise<Record<string, unknown>>;
}

export const test = base.extend<{ market: Server }>({
  market: async ({}, use) => {
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
        resolve('tests/e2e/fixtures/market-server.py'),
        '--dist',
        resolve('apps/desk-web/dist'),
        '--openssl',
        'C:/Program Files/Git/usr/bin/openssl.exe',
      ],
      { env, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true },
    );
    let readyResolve!: (origin: string) => void,
      readyReject!: (error: Error) => void;
    const ready = new Promise<string>((yes, no) => {
      readyResolve = yes;
      readyReject = no;
    });
    let counter = 0;
    const pending = new Map<number, (value: Record<string, unknown>) => void>();
    const lines = createInterface({ input: child.stdout });
    lines.on('line', (line) => {
      try {
        const item = JSON.parse(line);
        if (item.kind === 'ready') readyResolve(item.origin);
        else if (typeof item.id === 'number') {
          pending.get(item.id)?.(item);
          pending.delete(item.id);
        }
      } catch {
        readyReject(new Error('Invalid private TLS fixture response'));
      }
    });
    // Discard diagnostics rather than risk persisting private bootstrap material.
    child.stderr.resume();
    child.once('error', () =>
      readyReject(new Error('Cannot start TLS fixture')),
    );
    child.once('exit', () => {
      readyReject(new Error('TLS fixture exited'));
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
          () => reject(new Error('Private fixture command timeout')),
          5000,
        );
        timer.unref();
      });
      const value = await Promise.race([answer, timeout]);
      if (value.ok !== true) throw new Error('Private fixture command failed');
      return value;
    };
    try {
      const origin = await Promise.race([
        ready,
        new Promise<never>((_, reject) => {
          const timer = setTimeout(
            () => reject(new Error('TLS fixture readiness timeout')),
            20000,
          );
          timer.unref();
        }),
      ]);
      await use({ origin, command });
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
