import { spawn as spawnProcess } from 'node:child_process';
import type { ChildProcessWithoutNullStreams, SpawnOptionsWithoutStdio } from 'node:child_process';
import { classifySpawnPurpose, recordSpawn } from '@emdash/shared/perf';
import type { EnvSource } from '#primitives/exec/api';
import {
  ExecError,
  type BoundExec,
  type ExecBufferResult,
  type ExecOptions,
  type ExecResult,
  type ExecSpawnOptions,
} from './types';

const DEFAULT_MAX_BUFFER = 10 * 1024 * 1024;
const TIMEOUT_KILL_GRACE_MS = 1_000;

export type CreateBoundExecOptions = {
  file: string;
  cwd: string;
  env?: NodeJS.ProcessEnv | EnvSource;
};

export function createBoundExec(options: CreateBoundExecOptions): BoundExec {
  return new ProcessBoundExec(options.file, options.cwd, options.env);
}

type StdoutSink =
  | { kind: 'text'; chunks: string[] }
  | { kind: 'buffer'; chunks: Buffer[] }
  | { kind: 'stream'; onStdout: (chunk: string) => boolean | void };

class ProcessBoundExec implements BoundExec {
  constructor(
    readonly file: string,
    readonly cwd: string,
    readonly env?: NodeJS.ProcessEnv | EnvSource
  ) {}

  async exec(args: string[], options: ExecOptions = {}): Promise<ExecResult> {
    const chunks: string[] = [];
    const { stderr } = await this.run(args, options, { kind: 'text', chunks });
    return { stdout: chunks.join(''), stderr };
  }

  async execStreaming(
    args: string[],
    onStdout: (chunk: string) => boolean | void,
    options: ExecOptions = {}
  ): Promise<void> {
    await this.run(args, options, { kind: 'stream', onStdout });
  }

  async execBuffer(args: string[], options: ExecOptions = {}): Promise<ExecBufferResult> {
    const chunks: Buffer[] = [];
    const { stderr } = await this.run(args, options, { kind: 'buffer', chunks });
    return { stdout: Buffer.concat(chunks), stderr };
  }

  async spawn(
    args: string[],
    options: ExecSpawnOptions = {}
  ): Promise<ChildProcessWithoutNullStreams> {
    const env = await resolveEnv(this.env);
    recordSpawn(classifySpawnPurpose(this.file, args), this.file);
    return spawnProcess(this.file, args, {
      cwd: options.cwd ?? this.cwd,
      env: composeEnv(env, options.env),
      signal: options.signal,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  }

  withCwd(cwd: string): BoundExec {
    return new ProcessBoundExec(this.file, cwd, this.env);
  }

  private async run(
    args: string[],
    options: ExecOptions,
    sink: StdoutSink
  ): Promise<{ stderr: string }> {
    const env = await resolveEnv(this.env);
    return new Promise((resolve, reject) => {
      const spawnOptions: SpawnOptionsWithoutStdio = {
        cwd: options.cwd ?? this.cwd,
        env: composeEnv(env, options.env),
        detached: process.platform !== 'win32',
      };
      recordSpawn(classifySpawnPurpose(this.file, args), this.file);
      const child = spawnProcess(this.file, args, spawnOptions);
      const maxBuffer = options.maxBuffer ?? DEFAULT_MAX_BUFFER;
      let stderr = '';
      let stdoutBytes = 0;
      let stderrBytes = 0;
      let settled = false;
      let stopped = false;
      let terminationError: Error | undefined;
      let terminationPromise: Promise<void> | undefined;

      const stdoutText = (): string => {
        if (sink.kind === 'text') return sink.chunks.join('');
        if (sink.kind === 'buffer') return Buffer.concat(sink.chunks).toString('utf8');
        return '';
      };
      const fail = (error: unknown): void => {
        if (settled) return;
        settled = true;
        cleanup();
        reject(error);
      };
      const failExec = (exitCode: number | null, stderrOverride?: string): void => {
        fail(new ExecError(this.file, args, exitCode, stdoutText(), stderrOverride ?? stderr));
      };

      const startTermination = (error: Error): void => {
        if (settled || terminationError) return;
        terminationError = error;
        terminationPromise = terminateProcessGroup(child);
      };
      const timeout = options.timeoutMs
        ? setTimeout(() => {
            startTermination(
              new ExecError(
                this.file,
                args,
                null,
                stdoutText(),
                `Timed out after ${options.timeoutMs}ms`
              )
            );
          }, options.timeoutMs)
        : undefined;
      const abort = () => {
        startTermination(
          Object.assign(new Error('The operation was aborted'), {
            name: 'AbortError',
          })
        );
      };
      options.signal?.addEventListener('abort', abort, { once: true });
      if (options.signal?.aborted) abort();

      function cleanup(): void {
        if (timeout) clearTimeout(timeout);
        options.signal?.removeEventListener('abort', abort);
      }

      if (sink.kind !== 'buffer') child.stdout?.setEncoding('utf8');
      child.stderr?.setEncoding('utf8');

      child.stdout?.on('data', (chunk: string | Buffer) => {
        if (sink.kind === 'stream') {
          const shouldContinue = sink.onStdout(chunk as string);
          if (shouldContinue === false && !stopped) {
            stopped = true;
            child.kill();
          }
          return;
        }
        stdoutBytes += sink.kind === 'buffer' ? (chunk as Buffer).length : Buffer.byteLength(chunk);
        if (stdoutBytes > maxBuffer) {
          child.kill();
          failExec(null, 'stdout exceeded maxBuffer');
          return;
        }
        if (sink.kind === 'buffer') sink.chunks.push(chunk as Buffer);
        else sink.chunks.push(chunk as string);
      });

      child.stderr?.on('data', (chunk: string) => {
        options.onStderr?.(chunk);
        stderrBytes += Buffer.byteLength(chunk);
        if (stderrBytes > maxBuffer) {
          child.kill();
          failExec(null, 'stderr exceeded maxBuffer');
          return;
        }
        stderr += chunk;
      });

      child.on('error', (error) => {
        if (terminationError) return;
        if (error.name === 'AbortError') {
          fail(error);
          return;
        }
        failExec(null, error instanceof Error ? error.message : String(error));
      });

      child.on('close', async (code) => {
        cleanup();
        if (settled) return;
        if (terminationError) {
          await terminationPromise;
          settled = true;
          reject(terminationError);
          return;
        }
        settled = true;
        const exitCode = code ?? 0;
        if (exitCode === 0 || (sink.kind === 'stream' && stopped)) {
          resolve({ stderr });
          return;
        }
        reject(new ExecError(this.file, args, exitCode, stdoutText(), stderr));
      });
    });
  }
}

async function resolveEnv(
  env: NodeJS.ProcessEnv | EnvSource | undefined
): Promise<NodeJS.ProcessEnv | undefined> {
  return typeof env === 'function' ? await env() : env;
}

function composeEnv(
  base: NodeJS.ProcessEnv | undefined,
  overlay: NodeJS.ProcessEnv | undefined
): NodeJS.ProcessEnv | undefined {
  if (!base && !overlay) return undefined;
  if (!base) return { ...process.env, ...overlay };
  return overlay ? { ...base, ...overlay } : base;
}

async function terminateProcessGroup(child: ReturnType<typeof spawnProcess>): Promise<void> {
  signalProcessGroup(child, 'SIGTERM');
  if (await waitForProcessGroupExit(child, TIMEOUT_KILL_GRACE_MS)) return;
  signalProcessGroup(child, 'SIGKILL');
  await waitForProcessGroupExit(child, TIMEOUT_KILL_GRACE_MS);
}

function signalProcessGroup(child: ReturnType<typeof spawnProcess>, signal: NodeJS.Signals): void {
  if (child.pid && process.platform !== 'win32') {
    try {
      process.kill(-child.pid, signal);
      return;
    } catch {
      // The process may have exited between the timeout and the signal.
    }
  }
  child.kill(signal);
}

async function waitForProcessGroupExit(
  child: ReturnType<typeof spawnProcess>,
  timeoutMs: number
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (processGroupIsAlive(child) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  return !processGroupIsAlive(child);
}

function processGroupIsAlive(child: ReturnType<typeof spawnProcess>): boolean {
  if (!child.pid) return false;
  try {
    process.kill(process.platform === 'win32' ? child.pid : -child.pid, 0);
    return true;
  } catch {
    return false;
  }
}
