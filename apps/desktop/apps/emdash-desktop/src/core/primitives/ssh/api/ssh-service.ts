import type { ConnectionState, ConnectionTestResult, SshConfig, SshConfigHost } from './ssh';

export class SshConnectionNotFoundError extends Error {
  readonly name = 'SshConnectionNotFoundError';

  constructor(readonly connectionId: string) {
    super('SSH connection is no longer configured');
  }
}

/**
 * External surface of the SSH service: connection intent (connect/disconnect),
 * config-file host resolution, and transient connection testing. Config
 * parsing, credentials, and transport details stay implementation-private.
 */
export interface SshService {
  getSshConfigHosts(): Promise<SshConfigHost[]>;

  getSshConfigHost(alias: string): Promise<SshConfigHost>;

  /** Test a connection without persisting it or publishing connection events. */
  testConnection(
    config: SshConfig & { password?: string; passphrase?: string }
  ): Promise<ConnectionTestResult>;

  /** Intentionally close a connection and stop auto-reconnect. */
  disconnect(connectionId: string): Promise<void>;

  dropConnection(connectionId: string): Promise<void>;

  removeRuntimeState(connectionId: string): void;

  /** Ensure a connection is established (no-op if already connected). */
  connect(connectionId: string): Promise<ConnectionState>;

  /**
   * Ensure a connection for background consumers without changing user intent.
   * Explicitly disconnected machines remain disconnected until a user connects again.
   */
  ensureConnected(connectionId: string): Promise<ConnectionState>;
}
