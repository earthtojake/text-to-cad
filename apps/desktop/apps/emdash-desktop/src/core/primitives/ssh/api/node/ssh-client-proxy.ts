import type { Command } from '@emdash/core/primitives/exec/api';
import type { Client, ClientChannel } from 'ssh2';

export type SshExecOptions = {
  timeoutMs?: number;
  signal?: AbortSignal;
  maxStdoutBytes?: number;
  maxStderrBytes?: number;
};

export type SshExecResult = {
  stdout: string;
  stderr: string;
  exitCode: number;
};

/**
 * Stable reference to an ssh2 Client that survives reconnects.
 *
 * SSH-backed services hold a SshClientProxy rather than a raw Client. The
 * connection manager keeps the proxy pointed at the current live Client, so
 * callers that access proxy.client at call time always get the live
 * connection without needing to be rebuilt or replaced.
 */
export interface SshClientProxy {
  readonly connectionId: string;

  /**
   * The live ssh2 Client. Throws if the connection is not currently
   * established. Callers should check isConnected first if they want to
   * avoid throwing.
   */
  readonly client: Client;

  /** True while an active connection is held. */
  readonly isConnected: boolean;

  /** Opens an OpenSSH streamlocal channel through the current live connection. */
  forwardOutStreamLocal(socketPath: string): Promise<ClientChannel>;

  /** Runs a structured command through the current live connection with bounded resources. */
  exec(command: Command, options?: SshExecOptions): Promise<SshExecResult>;

  /** Runs an explicit POSIX shell script through the current live connection. */
  execScript(script: string, options?: SshExecOptions): Promise<SshExecResult>;
}
