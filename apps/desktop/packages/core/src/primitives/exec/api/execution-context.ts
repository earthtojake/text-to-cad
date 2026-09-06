/**
 * Options for a single exec call on an IExecutionContext.
 * Named distinctly from BoundExec's ExecOptions to avoid collisions.
 */
export type ExecContextOptions = {
  timeout?: number;
  maxBuffer?: number;
  signal?: AbortSignal;
};

export type ExecStreamingResult = {
  exitCode: number | null;
};

/** Resolves the environment to use for one subprocess spawn. */
export type EnvSource = () => Promise<Record<string, string | undefined>>;

/**
 * An execution context represents a host + optional working directory where
 * commands run. Implementations abstract the transport (local spawn vs SSH exec)
 * so consumers have no knowledge of whether they are running locally or remotely.
 */
export interface IExecutionContext {
  /** The working directory all commands run in. Undefined/empty = no cwd constraint. */
  readonly root?: string;

  /**
   * True only for LocalExecutionContext. Used by GitService to decide
   * whether to use CatFileBatch (local spawn) or git-show fallback (SSH).
   */
  readonly supportsLocalSpawn: boolean;

  /** Run a command and buffer all output. Rejects on non-zero exit code. */
  exec(
    command: string,
    args?: string[],
    opts?: ExecContextOptions
  ): Promise<{ stdout: string; stderr: string }>;

  /**
   * Refresh any cached shell environment for this context. Installers often
   * write shell startup files or install into paths that become visible only
   * after recapturing the user's shell environment.
   */
  refreshShellEnv?(): Promise<void>;

  /**
   * Run a command and stream stdout/stderr chunks to `onChunk`.
   * Resolves with the process exit code even when it is non-zero; callers
   * decide whether a non-zero exit is an error.
   * Return false from `onChunk` to abort the process early (resolves normally).
   * Passing `signal` rejects with an AbortError when the signal fires.
   */
  execStreaming(
    command: string,
    args: string[],
    onChunk: (chunk: string) => boolean,
    opts?: { signal?: AbortSignal }
  ): Promise<ExecStreamingResult>;

  /**
   * Abort all in-flight exec/execStreaming calls and release resources.
   * Idempotent - safe to call multiple times.
   */
  dispose(): void;
}
