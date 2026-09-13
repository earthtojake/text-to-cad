import { execFile, spawn } from 'node:child_process';
import { promisify } from 'node:util';
import { classifySpawnPurpose, recordSpawn } from '@emdash/shared/perf';
import type { EnvSource } from '#primitives/exec/api';
import type {
  ExecContextOptions,
  ExecStreamingResult,
  IExecutionContext,
} from './execution-context';
import type { ExecResult } from './types';

const execFileAsync = promisify(execFile);

export type NodeExecutionContextOptions = {
  root?: string;
  env?: NodeJS.ProcessEnv | EnvSource;
  refreshShellEnv?: () => Promise<void>;
};

export class NodeExecutionContext implements IExecutionContext {
  readonly supportsLocalSpawn = true;
  readonly root: string;

  private readonly lifetime = new AbortController();
  private readonly refreshShellEnvDelegate: (() => Promise<void>) | undefined;

  constructor(options: NodeExecutionContextOptions = {}) {
    this.root = options.root ?? '';
    this.env = options.env;
    this.refreshShellEnvDelegate = options.refreshShellEnv;
  }

  private readonly env: NodeJS.ProcessEnv | EnvSource | undefined;

  async exec(
    command: string,
    args: string[] = [],
    opts: ExecContextOptions = {}
  ): Promise<ExecResult> {
    const env = await this.resolveEnv();
    recordSpawn(classifySpawnPurpose(command, args), command);
    return (await execFileAsync(command, args, {
      cwd: this.root || undefined,
      env,
      timeout: opts.timeout,
      maxBuffer: opts.maxBuffer,
      signal: this.signal(opts.signal),
    })) as ExecResult;
  }

  async execStreaming(
    command: string,
    args: string[],
    onChunk: (chunk: string) => boolean,
    opts: { signal?: AbortSignal } = {}
  ): Promise<ExecStreamingResult> {
    const env = await this.resolveEnv();
    return new Promise((resolve, reject) => {
      const signal = this.signal(opts.signal);
      if (signal.aborted) {
        reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
        return;
      }

      recordSpawn(classifySpawnPurpose(command, args), command);
      const child = spawn(command, args, {
        cwd: this.root || undefined,
        env,
      });
      let settled = false;

      const onAbort = () => {
        if (settled) return;
        settled = true;
        child.kill('SIGTERM');
        reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
      };
      signal.addEventListener('abort', onAbort, { once: true });

      child.stdout.setEncoding('utf8');
      child.stdout.on('data', (chunk: string) => {
        if (!settled && !onChunk(chunk)) child.kill('SIGTERM');
      });
      child.stderr.setEncoding('utf8');
      child.stderr.on('data', (chunk: string) => {
        if (!settled) onChunk(chunk);
      });

      child.on('error', (error) => {
        signal.removeEventListener('abort', onAbort);
        if (settled) return;
        settled = true;
        reject(error);
      });
      child.on('close', (code) => {
        signal.removeEventListener('abort', onAbort);
        if (settled) return;
        settled = true;
        resolve({ exitCode: code });
      });
    });
  }

  dispose(): void {
    this.lifetime.abort();
  }

  async refreshShellEnv(): Promise<void> {
    await this.refreshShellEnvDelegate?.();
  }

  private signal(callerSignal?: AbortSignal): AbortSignal {
    return callerSignal
      ? AbortSignal.any([this.lifetime.signal, callerSignal])
      : this.lifetime.signal;
  }

  private async resolveEnv(): Promise<NodeJS.ProcessEnv | undefined> {
    return typeof this.env === 'function' ? await this.env() : this.env;
  }
}
