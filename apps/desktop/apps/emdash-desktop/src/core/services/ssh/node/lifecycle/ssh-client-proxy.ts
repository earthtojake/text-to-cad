import { formatCommandLine, type Command } from '@emdash/core/primitives/exec/api';
import type { Client, ClientChannel } from 'ssh2';
import type {
  SshClientProxy as SshClientProxyContract,
  SshExecOptions,
  SshExecResult,
} from '@core/primitives/ssh/api/node/ssh-client-proxy';
import { execOnClient } from '../operations/exec';
import { forwardOutStreamLocalOnClient } from '../operations/streamlocal';

/**
 * Stable reference to an ssh2 Client that survives reconnects.
 *
 * SSH-backed services hold a SshClientProxy rather than a raw Client.
 * SshConnectionManager calls update() each time
 * a connection is established (including after reconnect) and invalidate()
 * when the connection drops. Callers that access proxy.client at call time
 * therefore always get the current live Client without needing to be
 * rebuilt or replaced.
 */
export class SshClientProxy implements SshClientProxyContract {
  private _client: Client | null = null;

  constructor(readonly connectionId: string) {}

  /** Called by SshConnectionManager when a connection becomes ready. */
  update(client: Client): void {
    this._client = client;
  }

  /** Called by SshConnectionManager when the connection drops. */
  invalidate(): void {
    this._client = null;
  }

  /**
   * The live ssh2 Client. Throws if the connection is not currently
   * established. Callers should check isConnected first if they want to
   * avoid throwing.
   */
  get client(): Client {
    if (!this._client) {
      throw new Error('SSH connection is not available');
    }
    return this._client;
  }

  /** True while an active connection is held. */
  get isConnected(): boolean {
    return this._client !== null;
  }

  /** Opens an OpenSSH streamlocal channel through the current live connection. */
  forwardOutStreamLocal(socketPath: string): Promise<ClientChannel> {
    return forwardOutStreamLocalOnClient(this.client, socketPath);
  }

  /** Runs a structured command through the current live connection with bounded resources. */
  exec(command: Command, options?: SshExecOptions): Promise<SshExecResult> {
    return execOnClient(this.client, formatCommandLine(command, 'posix'), options);
  }

  /** Runs an explicit POSIX shell script through the current live connection. */
  execScript(script: string, options?: SshExecOptions): Promise<SshExecResult> {
    return execOnClient(this.client, script, options);
  }
}
