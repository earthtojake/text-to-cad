import { spawn } from 'node:child_process';
import type { ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import os from 'node:os';
import { err, ok, type Result } from '@emdash/shared';
import { recordSpawn } from '@emdash/shared/perf';
import { SHELL_ENV_CAPTURE_GUARD, type ShellEnvCapture, type ShellEnvCaptureError } from './types';

export type CaptureShellEnvOptions = {
  readonly baseEnv?: NodeJS.ProcessEnv;
  readonly timeoutMs?: number;
  readonly now?: () => number;
};

const MAX_CAPTURE_BYTES = 1024 * 1024;
const TIMEOUT_KILL_GRACE_MS = 250;

type ShellProbeResult =
  | {
      readonly success: true;
      readonly stdout: string;
      readonly stderr: string;
      readonly status: number;
    }
  | { readonly success: false; readonly message: string };

export function parseEnvOutput(raw: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of raw.split('\n')) {
    const eq = line.indexOf('=');
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1);
    if (key && /^[A-Za-z_]\w*$/.test(key)) {
      result[key] = value;
    }
  }
  return result;
}

export async function captureShellEnv(
  options: CaptureShellEnvOptions = {}
): Promise<Result<ShellEnvCapture, ShellEnvCaptureError>> {
  const baseEnv = options.baseEnv ?? process.env;
  const now = options.now ?? Date.now;

  if (process.platform === 'win32') {
    return ok({
      env: withoutCaptureGuard(stringEnv(baseEnv)),
      source: 'windows',
      capturedAt: now(),
    });
  }

  const shell = resolveLoginShell(baseEnv);
  const result = await runShellEnvProbe(shell, baseEnv, options.timeoutMs ?? 5_000);

  if (!result.success) {
    return err({
      type: 'capture-failed',
      shell,
      message: result.message,
    });
  }

  if (result.status !== 0) {
    return err({
      type: 'capture-failed',
      shell,
      message: result.stderr.trim() || `shell env capture exited with status ${result.status}`,
    });
  }

  return ok({
    env: withoutCaptureGuard(parseEnvOutput(result.stdout)),
    source: 'login-shell',
    capturedAt: now(),
  });
}

function runShellEnvProbe(
  shell: string,
  baseEnv: NodeJS.ProcessEnv,
  timeoutMs: number
): Promise<ShellProbeResult> {
  return new Promise((resolve) => {
    let child: ChildProcess;
    try {
      recordSpawn('shell', shell);
      child = spawn(shell, ['-ilc', 'env'], {
        env: {
          ...baseEnv,
          ...SHELL_ENV_CAPTURE_GUARD,
        },
        detached: true,
        stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (error) {
      resolve({
        success: false,
        message: error instanceof Error ? error.message : String(error),
      });
      return;
    }

    let stdout = '';
    let stderr = '';
    let stdoutBytes = 0;
    let stderrBytes = 0;
    let settled = false;

    const finish = (result: ShellProbeResult, terminate = false): void => {
      if (settled) return;
      settled = true;
      if (timeout) clearTimeout(timeout);
      if (terminate) terminateProcessGroup(child);
      resolve(result);
    };
    const timeout =
      timeoutMs > 0
        ? setTimeout(() => {
            finish(
              {
                success: false,
                message: `shell env capture timed out after ${timeoutMs}ms`,
              },
              true
            );
          }, timeoutMs)
        : undefined;
    timeout?.unref();

    child.stdout?.setEncoding('utf8');
    child.stderr?.setEncoding('utf8');

    child.stdout?.on('data', (chunk: string) => {
      if (settled) return;
      stdoutBytes += Buffer.byteLength(chunk);
      if (stdoutBytes > MAX_CAPTURE_BYTES) {
        finish({ success: false, message: 'shell env capture stdout exceeded maxBuffer' }, true);
        return;
      }
      stdout += chunk;
    });

    child.stderr?.on('data', (chunk: string) => {
      if (settled) return;
      stderrBytes += Buffer.byteLength(chunk);
      if (stderrBytes > MAX_CAPTURE_BYTES) {
        finish({ success: false, message: 'shell env capture stderr exceeded maxBuffer' }, true);
        return;
      }
      stderr += chunk;
    });

    child.on('error', (error) => {
      finish({ success: false, message: error.message });
    });

    child.on('close', (status) => {
      if (status === null) {
        finish({ success: false, message: 'shell env capture exited without a status' });
        return;
      }
      finish({ success: true, stdout, stderr, status });
    });
  });
}

function terminateProcessGroup(child: ChildProcess): void {
  signalProcessGroup(child, 'SIGTERM');
  const escalation = setTimeout(() => {
    signalProcessGroup(child, 'SIGKILL');
  }, TIMEOUT_KILL_GRACE_MS);
  escalation.unref();
}

function signalProcessGroup(child: ChildProcess, signal: NodeJS.Signals): void {
  if (child.exitCode !== null || child.signalCode !== null) return;
  if (child.pid && process.platform !== 'win32') {
    try {
      process.kill(-child.pid, signal);
      return;
    } catch {
      // The process group may have exited between the timeout and this signal.
    }
  }
  child.kill(signal);
}

function withoutCaptureGuard(env: Record<string, string>): Record<string, string> {
  for (const key of Object.keys(SHELL_ENV_CAPTURE_GUARD)) {
    delete env[key];
  }
  return env;
}

export function resolveLoginShell(env: NodeJS.ProcessEnv = process.env): string {
  return candidateShells(env).find((candidate) => existsSync(candidate)) ?? '/bin/sh';
}

function candidateShells(env: NodeJS.ProcessEnv): string[] {
  const candidates = [env.SHELL, userShell(), '/bin/bash', '/bin/sh'].filter(
    (candidate): candidate is string => typeof candidate === 'string' && candidate.length > 0
  );
  return [...new Set(candidates)];
}

function userShell(): string | undefined {
  try {
    return os.userInfo().shell ?? undefined;
  } catch {
    return undefined;
  }
}

function stringEnv(env: NodeJS.ProcessEnv): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(env)) {
    if (typeof value === 'string') result[key] = value;
  }
  return result;
}
