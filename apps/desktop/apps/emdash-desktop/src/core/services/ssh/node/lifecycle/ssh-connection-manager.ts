import { EventEmitter } from 'node:events';
import { retrySchedules, type RetrySchedule } from '@emdash/shared/scheduling';
import ssh2, { type Client } from 'ssh2';
import type { ConnectionState, SshConnectionEvent, SshHealthState } from '@core/primitives/ssh/api';
import type {
  SshConnectionManager as SshConnectionManagerContract,
  SshConnectionManagerEvent,
} from '@core/primitives/ssh/api/node/ssh-connection-manager';
import type { SshConnectResult } from '../connect/resolve-ssh-connect-config';
import { SshClientProxy } from './ssh-client-proxy';

const { Client: Ssh2Client } = ssh2;

// ─── Error classes ────────────────────────────────────────────────────────────

export class SshAuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SshAuthError';
  }
}

export class SshTimeoutError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SshTimeoutError';
  }
}

export class SshConnectionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SshConnectionError';
  }
}

// ─── Types ────────────────────────────────────────────────────────────────────

/** Delays between successive reconnect attempts; exhausting the sequence gives up. */
const RECONNECT_SCHEDULE: RetrySchedule = retrySchedules.sequence([
  1_000, 2_000, 5_000, 10_000, 20_000,
]);

interface ReconnectState {
  attempt: number;
  timer: NodeJS.Timeout | undefined;
}

type SshConnectionManagerLog = {
  info: (message: string, metadata?: Record<string, unknown>) => void;
  warn: (message: string, metadata?: Record<string, unknown>) => void;
  error: (message: string, metadata?: Record<string, unknown>) => void;
};

export interface SshConnectionManagerDeps {
  createClient?: () => Client;
  publishEvent?: (event: SshConnectionEvent) => void;
  log?: SshConnectionManagerLog;
}

const noopLog: SshConnectionManagerLog = {
  info: () => {},
  warn: () => {},
  error: () => {},
};

// ─── Implementation ──────────────────────────────────────────────────────────

export class SshConnectionManager extends EventEmitter implements SshConnectionManagerContract {
  private readonly deps: Required<SshConnectionManagerDeps>;

  constructor(deps: SshConnectionManagerDeps = {}) {
    super();
    this.deps = {
      createClient: deps.createClient ?? (() => new Ssh2Client()),
      publishEvent: deps.publishEvent ?? (() => {}),
      log: deps.log ?? noopLog,
    };
  }

  /** One stable proxy per connection ID — survives reconnects. */
  private proxies: Map<string, SshClientProxy> = new Map();

  /** Re-resolved for every initial connection and reconnect attempt. */
  private connectionResolvers: Map<string, () => Promise<SshConnectResult>> = new Map();

  private pendingConnections: Map<string, Promise<SshClientProxy>> = new Map();

  /** Tracks ongoing reconnect backoff state per connection. */
  private reconnecting: Map<string, ReconnectState> = new Map();

  private ephemeralConnections: Set<string> = new Set();

  private connectionCleanups: Map<string, () => void> = new Map();

  private activeClients: Map<string, Client> = new Map();

  private connectionGenerations: Map<string, number> = new Map();

  private healthStates: Map<string, SshHealthState> = new Map();

  /**
   * IDs for which dropConnection() was called — these are excluded from
   * auto-reconnect so an intentional teardown is never silently restarted.
   */
  private intentionalDisconnects: Set<string> = new Set();

  // ─── Public API ──────────────────────────────────────────────────────────

  /**
   * Resolve, connect, and register a client under the given ID.
   *
   * - Reuses an existing connection if already in the pool.
   * - Concurrent calls for the same ID coalesce to a single attempt.
   * - Invokes the supplied resolver again for every reconnect attempt.
   * - Throws SshAuthError, SshTimeoutError, or SshConnectionError on failure.
   */
  async createConnection(
    id: string,
    resolve: () => Promise<SshConnectResult>,
    options: { ephemeral?: boolean } = {}
  ): Promise<SshClientProxy> {
    this.intentionalDisconnects.delete(id);
    this.connectionResolvers.set(id, resolve);
    if (options.ephemeral) {
      this.ephemeralConnections.add(id);
    } else {
      this.ephemeralConnections.delete(id);
    }

    const existing = this.proxies.get(id);
    if (existing?.isConnected) return existing;

    const pending = this.pendingConnections.get(id);
    if (pending) return await pending;

    const generation = this.nextConnectionGeneration(id);
    this.emitConnecting(id);
    const connectionPromise = this.resolveAndConnect(id, resolve, generation);
    this.pendingConnections.set(id, connectionPromise);
    try {
      return await connectionPromise;
    } finally {
      if (this.pendingConnections.get(id) === connectionPromise) {
        this.pendingConnections.delete(id);
      }
    }
  }

  private async resolveAndConnect(
    id: string,
    resolve: () => Promise<SshConnectResult>,
    generation: number
  ): Promise<SshClientProxy> {
    const resolved = await resolve();
    if (
      !this.isCurrentConnectionGeneration(id, generation) ||
      this.intentionalDisconnects.has(id)
    ) {
      resolved.cleanup();
      throw new SshConnectionError(`SSH connection '${id}' was disconnected before connecting`);
    }

    return await this.connectResolved(id, resolved, generation);
  }

  /** Get the stable SshClientProxy for a connection, or undefined. */
  getProxy(id: string): SshClientProxy | undefined {
    return this.proxies.get(id);
  }

  /** Returns true if the connection is currently live. */
  isConnected(id: string): boolean {
    return this.proxies.get(id)?.isConnected ?? false;
  }

  /** IDs of all connections that have a proxy (connected or reconnecting). */
  getConnectionIds(): string[] {
    return Array.from(this.proxies.keys()).filter((id) => !this.isEphemeral(id));
  }

  /** Returns the current ConnectionState for a single connection ID. */
  getConnectionState(id: string): ConnectionState {
    if (this.proxies.get(id)?.isConnected) return 'connected';
    if (this.reconnecting.has(id)) return 'reconnecting';
    if (this.pendingConnections.has(id)) return 'connecting';
    return 'disconnected';
  }

  /** Returns the current ConnectionState for every tracked connection. */
  getAllConnectionStates(): Record<string, ConnectionState> {
    const result: Record<string, ConnectionState> = {};
    for (const id of this.proxies.keys()) {
      if (this.isEphemeral(id)) continue;
      result[id] = this.getConnectionState(id);
    }
    for (const id of this.pendingConnections.keys()) {
      if (this.isEphemeral(id)) continue;
      result[id] = this.getConnectionState(id);
    }
    return result;
  }

  getAllHealthStates(): Record<string, SshHealthState> {
    return Object.fromEntries(
      Array.from(this.healthStates).filter(([id]) => !this.isEphemeral(id))
    );
  }

  /**
   * Gracefully close a connection and permanently stop reconnection for it.
   * This is an intentional teardown — auto-reconnect will NOT fire afterward.
   */
  async dropConnection(id: string): Promise<void> {
    this.intentionalDisconnects.add(id);
    const generation = this.nextConnectionGeneration(id);
    this.cancelReconnect(id);
    this.connectionResolvers.delete(id);

    const proxy = this.proxies.get(id);
    if (!proxy?.isConnected) {
      this.deps.log.warn(
        'SshConnectionManager: disconnect called for unknown/inactive connection',
        {
          connectionId: id,
        }
      );
      const client = this.activeClients.get(id);
      if (client) {
        client.destroy();
      }
      this.runConnectionCleanup(id);
      this.proxies.delete(id);
      this.pendingConnections.delete(id);
      this.clearRegistration(id, generation);
      return;
    }

    this.deps.log.info('SshConnectionManager: disconnecting', { connectionId: id });

    const client = proxy.client;
    return new Promise<void>((resolve) => {
      const timeout = setTimeout(() => {
        this.deps.log.warn('SshConnectionManager: disconnect timed out, forcing close', {
          connectionId: id,
        });
        client.destroy();
        proxy.invalidate();
        this.proxies.delete(id);
        this.runConnectionCleanup(id);
        this.clearRegistration(id, generation);
        resolve();
      }, 5_000);

      client.once('close', () => {
        clearTimeout(timeout);
        proxy.invalidate();
        this.proxies.delete(id);
        this.runConnectionCleanup(id);
        this.clearRegistration(id, generation);
        resolve();
      });

      client.end();
    });
  }

  /** Gracefully close all connections. */
  async disconnectAll(): Promise<void> {
    const ids = Array.from(new Set([...this.proxies.keys(), ...this.pendingConnections.keys()]));
    this.deps.log.info('SshConnectionManager: disconnecting all connections', {
      count: ids.length,
    });
    await Promise.all(ids.map((id) => this.dropConnection(id)));
  }

  // ─── Private ─────────────────────────────────────────────────────────────

  private connectResolved(
    id: string,
    resolvedConnection: SshConnectResult,
    generation: number
  ): Promise<SshClientProxy> {
    const { config, cleanup } = resolvedConnection;
    this.deps.log.info('SshConnectionManager: creating connection', {
      connectionId: id,
      host: config.host,
      username: config.username,
    });

    // Ensure a stable proxy exists for this ID.
    const proxy = this.proxies.get(id) ?? new SshClientProxy(id);
    this.proxies.set(id, proxy);

    const client = this.deps.createClient();
    let cleanupCalled = false;
    const cleanupOnce = () => {
      if (cleanupCalled) return;
      cleanupCalled = true;
      this.connectionCleanups.delete(id);
      if (this.activeClients.get(id) === client) {
        this.activeClients.delete(id);
      }
      cleanup();
    };
    this.activeClients.set(id, client);
    this.connectionCleanups.set(id, cleanupOnce);

    return new Promise((resolve, reject) => {
      let resolved = false;
      let connectedBeforeClose = false;
      let disconnectedEmitted = false;
      const resolveOnce = (p: SshClientProxy) => {
        if (!resolved) {
          resolved = true;
          resolve(p);
        }
      };
      const emitDisconnectedOnce = () => {
        if (disconnectedEmitted) return;
        disconnectedEmitted = true;
        this.emitConnectionEvent(
          { type: 'disconnected', connectionId: id },
          { type: 'disconnected', connectionId: id }
        );
      };

      client.on('error', (error: Error) => {
        this.deps.log.error('SshConnectionManager: connection error', {
          connectionId: id,
          error: error.message,
        });

        this.emitConnectionEvent(
          { type: 'error', connectionId: id, error },
          { type: 'error', connectionId: id, errorMessage: error.message }
        );

        if (proxy.isConnected && proxy.client === client) {
          connectedBeforeClose = true;
          proxy.invalidate();
          emitDisconnectedOnce();
        }
        cleanupOnce();
        reject(classifyError(error));
      });

      client.on('close', () => {
        this.deps.log.info('SshConnectionManager: connection closed', { connectionId: id });

        if (!resolved) {
          cleanupOnce();
          reject(new SshConnectionError('SSH connection closed before ready'));
          return;
        }

        // Only react if this client is still the one backing the proxy.
        if ((proxy.isConnected && proxy.client === client) || connectedBeforeClose) {
          const wasConnected = proxy.isConnected && proxy.client === client;
          proxy.invalidate();

          emitDisconnectedOnce();
          cleanupOnce();

          // Auto-reconnect unless this was an intentional disconnect or the
          // initial handshake never succeeded (resolved = false still).
          if (
            !this.intentionalDisconnects.has(id) &&
            !this.isEphemeral(id) &&
            resolved &&
            (wasConnected || connectedBeforeClose)
          ) {
            this.scheduleReconnect(id);
          }
        }
      });

      client.on('ready', () => {
        this.deps.log.info('SshConnectionManager: connection ready', { connectionId: id });

        if (
          !this.isCurrentConnectionGeneration(id, generation) ||
          this.intentionalDisconnects.has(id)
        ) {
          cleanupOnce();
          client.end();
          reject(new SshConnectionError(`SSH connection '${id}' was disconnected before ready`));
          return;
        }

        proxy.update(client);
        this.clearHealthState(id);

        const isReconnect = this.reconnecting.has(id);
        this.cancelReconnect(id);

        this.emitConnectionEvent(
          {
            type: isReconnect ? 'reconnected' : 'connected',
            connectionId: id,
            proxy,
          },
          {
            type: isReconnect ? 'reconnected' : 'connected',
            connectionId: id,
          }
        );

        resolveOnce(proxy);
      });

      try {
        client.connect(config);
      } catch (error) {
        cleanupOnce();
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  private scheduleReconnect(id: string): void {
    if (this.intentionalDisconnects.has(id) || this.isEphemeral(id)) return;

    const state = this.reconnecting.get(id) ?? { attempt: 0, timer: undefined };
    const attempt = state.attempt + 1;

    const delayMs = RECONNECT_SCHEDULE.delayFor(attempt - 1);
    if (delayMs === undefined) {
      this.deps.log.error('SshConnectionManager: max reconnect attempts reached', {
        connectionId: id,
      });
      this.reconnecting.delete(id);
      this.emitConnectionEvent(
        { type: 'reconnect-failed', connectionId: id },
        { type: 'reconnect-failed', connectionId: id }
      );
      return;
    }

    this.deps.log.info('SshConnectionManager: scheduling reconnect', {
      connectionId: id,
      attempt,
      delayMs,
    });

    this.emitConnectionEvent(
      { type: 'reconnecting', connectionId: id, attempt, delayMs },
      { type: 'reconnecting', connectionId: id, attempt, delayMs }
    );

    const timer = setTimeout(() => {
      if (this.intentionalDisconnects.has(id)) {
        this.reconnecting.delete(id);
        return;
      }

      const resolve = this.connectionResolvers.get(id);
      if (!resolve) {
        this.reconnecting.delete(id);
        return;
      }

      void this.createConnection(id, resolve).catch((error: unknown) => {
        // Auth failures won't resolve with retries — stop immediately.
        if (error instanceof SshAuthError) {
          this.deps.log.error('SshConnectionManager: reconnect stopped — auth failure', {
            connectionId: id,
          });
          this.reconnecting.delete(id);
          this.emitConnectionEvent(
            { type: 'reconnect-failed', connectionId: id },
            { type: 'reconnect-failed', connectionId: id }
          );
        } else if (this.intentionalDisconnects.has(id)) {
          this.reconnecting.delete(id);
        } else {
          this.scheduleReconnect(id);
        }
      });
    }, delayMs);

    this.reconnecting.set(id, { attempt, timer });
  }

  private cancelReconnect(id: string): void {
    const state = this.reconnecting.get(id);
    if (state?.timer !== undefined) {
      clearTimeout(state.timer);
    }
    this.reconnecting.delete(id);
  }

  private runConnectionCleanup(id: string): void {
    this.connectionCleanups.get(id)?.();
  }

  private emitConnecting(id: string): void {
    this.emitConnectionEvent(
      { type: 'connecting', connectionId: id },
      { type: 'connecting', connectionId: id }
    );
  }

  private nextConnectionGeneration(id: string): number {
    const next = (this.connectionGenerations.get(id) ?? 0) + 1;
    this.connectionGenerations.set(id, next);
    return next;
  }

  private isCurrentConnectionGeneration(id: string, generation: number): boolean {
    return this.connectionGenerations.get(id) === generation;
  }

  private clearRegistration(id: string, generation: number): void {
    if (!this.isCurrentConnectionGeneration(id, generation)) return;
    this.connectionResolvers.delete(id);
    this.ephemeralConnections.delete(id);
  }

  private isEphemeral(id: string): boolean {
    return this.ephemeralConnections.has(id);
  }

  private emitConnectionEvent(
    managerEvent: SshConnectionManagerEvent,
    publishedEvent: SshConnectionEvent
  ): void {
    if (this.isEphemeral(managerEvent.connectionId)) return;
    this.emit('connection-event', managerEvent);
    this.deps.publishEvent(publishedEvent);
  }

  private clearHealthState(connectionId: string): SshHealthState {
    const health: SshHealthState = { status: 'ok' };
    if (this.healthStates.delete(connectionId)) {
      this.emitHealthChanged(connectionId, health);
    }
    return health;
  }

  private emitHealthChanged(connectionId: string, health: SshHealthState): void {
    if (this.isEphemeral(connectionId)) return;
    this.deps.publishEvent({
      type: 'health-changed',
      connectionId,
      health,
    });
  }
}

function classifyError(error: Error): SshAuthError | SshTimeoutError | SshConnectionError {
  const msg = error.message.toLowerCase();
  if (msg.includes('authentication') || msg.includes('auth') || msg.includes('permission denied')) {
    return new SshAuthError(error.message);
  }
  if (msg.includes('timeout') || msg.includes('timed out')) {
    return new SshTimeoutError(error.message);
  }
  return new SshConnectionError(error.message);
}
