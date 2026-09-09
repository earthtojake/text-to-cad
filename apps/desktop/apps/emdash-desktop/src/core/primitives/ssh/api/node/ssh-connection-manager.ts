import type { ConnectionState, SshHealthState } from '../ssh';
import type { SshClientProxy } from './ssh-client-proxy';

/**
 * In-process lifecycle event emitted by the SSH connection manager. Unlike
 * SshConnectionEvent (the published wire event), this carries the live client
 * proxy and error objects for main-process consumers.
 */
export type SshConnectionManagerEvent =
  | { type: 'connecting'; connectionId: string }
  | { type: 'connected'; connectionId: string; proxy: SshClientProxy }
  | { type: 'disconnected'; connectionId: string }
  | { type: 'reconnecting'; connectionId: string; attempt: number; delayMs: number }
  | { type: 'reconnected'; connectionId: string; proxy: SshClientProxy }
  | { type: 'reconnect-failed'; connectionId: string }
  | { type: 'error'; connectionId: string; error: Error };

export type SshConnectionManagerListener = (event: SshConnectionManagerEvent) => void;

/**
 * External surface of the SSH connection manager: connection state reads,
 * proxy access, teardown, and lifecycle event subscription. Establishing
 * connections stays implementation-private in the ssh service.
 */
export interface SshConnectionManager {
  /** Get the stable SshClientProxy for a connection, or undefined. */
  getProxy(id: string): SshClientProxy | undefined;

  /** Returns true if the connection is currently live. */
  isConnected(id: string): boolean;

  /** IDs of all connections that have a proxy (connected or reconnecting). */
  getConnectionIds(): string[];

  /** Returns the current ConnectionState for a single connection ID. */
  getConnectionState(id: string): ConnectionState;

  /** Returns the current ConnectionState for every tracked connection. */
  getAllConnectionStates(): Record<string, ConnectionState>;

  getAllHealthStates(): Record<string, SshHealthState>;

  /**
   * Gracefully close a connection and permanently stop reconnection for it.
   * This is an intentional teardown — auto-reconnect will NOT fire afterward.
   */
  dropConnection(id: string): Promise<void>;

  /** Gracefully close all connections. */
  disconnectAll(): Promise<void>;

  on(event: 'connection-event', listener: SshConnectionManagerListener): this;
  off(event: 'connection-event', listener: SshConnectionManagerListener): this;
}
