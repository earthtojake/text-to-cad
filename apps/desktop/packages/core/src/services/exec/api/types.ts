import type { ChildProcessWithoutNullStreams } from 'node:child_process';
import type { EnvSource } from '#primitives/exec/api';

export type ExecOptions = {
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  maxBuffer?: number;
  onStderr?: (chunk: string) => void;
  signal?: AbortSignal;
  timeoutMs?: number;
};

export type ExecSpawnOptions = Pick<ExecOptions, 'cwd' | 'env' | 'signal'>;

export type ExecResult = {
  stdout: string;
  stderr: string;
};

export type ExecBufferResult = {
  stdout: Buffer;
  stderr: string;
};

export class ExecError extends Error {
  constructor(
    readonly file: string,
    readonly args: readonly string[],
    readonly exitCode: number | null,
    readonly stdout: string,
    readonly stderr: string
  ) {
    super(`${file} ${args.join(' ')} failed (exit ${exitCode ?? 'unknown'})`);
    this.name = 'ExecError';
  }
}

export type BoundExec = {
  readonly file: string;
  readonly cwd: string;
  readonly env?: NodeJS.ProcessEnv | EnvSource;
  exec(args: string[], options?: ExecOptions): Promise<ExecResult>;
  execStreaming(
    args: string[],
    onStdout: (chunk: string) => boolean | void,
    options?: ExecOptions
  ): Promise<void>;
  execBuffer(args: string[], options?: ExecOptions): Promise<ExecBufferResult>;
  spawn(
    args: string[],
    options?: ExecSpawnOptions
  ): ChildProcessWithoutNullStreams | Promise<ChildProcessWithoutNullStreams>;
  withCwd(cwd: string): BoundExec;
};
