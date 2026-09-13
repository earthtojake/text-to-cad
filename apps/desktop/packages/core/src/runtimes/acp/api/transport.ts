import type { Readable, Writable } from 'node:stream';
import type { TerminalExit } from '#runtimes/acp/api/models/terminals';

/** Exit status of a terminal command — mirrors the ACP WaitForTerminalExitResponse shape. */
export type AcpTerminalExit = TerminalExit;

/**
 * A running command spawned by the client on behalf of an ACP agent.
 * The runtime buffers its combined stdout+stderr output; the host only
 * provides the raw streams, exit callback, and kill primitive.
 */
export interface AcpTerminalProcess {
  /** Combined output stream (stdout; stderr is merged in at the host level if available). */
  readonly stdout: Readable;
  /** Separate stderr stream when the host can provide it separately. */
  readonly stderr?: Readable;
  /** Exit code if the process has already exited, null otherwise. */
  readonly exitCode: number | null;
  /** Register a callback to be called when the process exits. */
  onExit(cb: (status: AcpTerminalExit) => void): void;
  /** Register a callback to be called if the process emits an error. */
  onError(cb: (err: Error) => void): void;
  /** Send a termination signal to the process. */
  kill(signal?: NodeJS.Signals): void;
}

/**
 * Uniform view of a running agent process, regardless of whether it is a local
 * child process or a remote SSH exec channel.
 */
export interface AcpProcessHandle {
  /** JSON-RPC framing input (writable end of the stdio pipe). */
  readonly stdin: Writable;
  /** JSON-RPC framing output (readable end of the stdio pipe). */
  readonly stdout: Readable;
  /** Optional separate stderr stream (not available on PTY channels). */
  readonly stderr?: Readable;
  /** Exit code if the process has already exited, null otherwise. */
  readonly exitCode: number | null;
  /** Register a callback to be called when the process exits. */
  onExit(cb: (code: number | null) => void): void;
  /** Register a callback to be called if the process emits an error. */
  onError(cb: (err: Error) => void): void;
  /** Send a termination signal to the process. */
  kill(signal?: NodeJS.Signals): void;
}

export interface AcpFs {
  readFile(path: string, encoding: 'utf8'): Promise<string>;
  writeFile(path: string, content: string, encoding: 'utf8'): Promise<void>;
  mkdir(path: string, opts: { recursive: boolean }): Promise<unknown>;
}

/**
 * Represents a specific machine's ACP process host: can resolve the agent
 * executable + env for a given provider, spawn an agent process, and provide a
 * file-system adapter for the ACP client file handlers.
 */
export interface AcpProcessHost {
  /**
   * Resolve the agent CLI path and environment variables for the given provider.
   * The host impl looks up binary names and cached paths internally.
   */
  resolveSpawnContext(
    providerId: string
  ): Promise<{ cli: string; agentEnv: Record<string, string> }>;

  /**
   * Spawn the agent process and return a handle to its stdio streams.
   */
  spawn(spec: {
    command: string;
    args: string[];
    env: Record<string, string>;
    cwd: string;
  }): Promise<AcpProcessHandle>;

  /**
   * Spawn a terminal command on behalf of an ACP agent.
   * Optional — omit on hosts that cannot host agent terminals.
   * When present the runtime will advertise `terminal: true` in `clientCapabilities`.
   */
  spawnTerminal?(spec: {
    command: string;
    args: string[];
    env: Record<string, string>;
    cwd: string;
  }): Promise<AcpTerminalProcess>;

  /** File system adapter scoped to the remote or local machine. */
  readonly fs: AcpFs;
}
