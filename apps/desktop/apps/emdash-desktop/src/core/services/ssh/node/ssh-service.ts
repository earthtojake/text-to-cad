import { randomUUID } from 'node:crypto';
import { eq } from 'drizzle-orm';
import type {
  ConnectionState,
  ConnectionTestResult,
  SshConfigHost,
  SshConfig,
  SshService as SshServiceContract,
} from '@core/primitives/ssh/api';
import { SshConnectionNotFoundError } from '@core/primitives/ssh/api';
import type { AppDb } from '@core/services/app-db/node/db';
import {
  sshConnections as sshConnectionsTable,
  type SshConnectionRow,
} from '@core/services/app-db/node/schema';
import type { ResolvedSshConfig } from './config/resolve-ssh-config';
import type { SshConnectInput, SshConnectResult } from './connect/resolve-ssh-connect-config';
import type { SshConnectionsModel } from './connections-model';
import type { SshConnectionManager } from './lifecycle/ssh-connection-manager';

type SshServiceLog = {
  warn(message: string, metadata?: Record<string, unknown>): void;
};

type SshServiceTelemetry = {
  capture(event: 'ssh_connection_attempted', properties: { success: boolean }): void;
};

export interface SshServiceDeps {
  db: AppDb;
  manager: SshConnectionManager;
  runtime: Pick<SshConnectionsModel, 'remove'>;
  resolveConnectConfig(input: SshConnectInput): Promise<SshConnectResult>;
  parseSshConfigFile(): Promise<SshConfigHost[]>;
  resolveSshConfig(alias: string): Promise<ResolvedSshConfig>;
  telemetry: SshServiceTelemetry;
  log: SshServiceLog;
  createId?: () => string;
  now?: () => number;
}

export class SshService implements SshServiceContract {
  private readonly createId: () => string;
  private readonly now: () => number;

  constructor(private readonly deps: SshServiceDeps) {
    this.createId = deps.createId ?? randomUUID;
    this.now = deps.now ?? Date.now;
  }

  async getSshConfigHosts(): Promise<SshConfigHost[]> {
    return await this.deps.parseSshConfigFile();
  }

  async getSshConfigHost(alias: string): Promise<SshConfigHost> {
    const resolved = await this.deps.resolveSshConfig(alias);
    return {
      host: alias,
      hostname: resolved.hostname,
      user: resolved.user,
      port: resolved.port,
      identityFile: resolved.identityFile[0],
      identityAgent: resolved.identityAgent,
      proxyJump: resolved.proxyJump,
      proxyCommand: resolved.proxyCommand,
      forwardAgent: resolved.forwardAgent,
      forwardAgentValue: resolved.forwardAgentValue,
    };
  }

  /** Test a connection without persisting it or publishing connection events. */
  async testConnection(
    config: SshConfig & { password?: string; passphrase?: string }
  ): Promise<ConnectionTestResult> {
    const connectionId = this.createId();
    const startedAt = this.now();
    let debugLogs: string[] = [];
    let result: ConnectionTestResult;

    try {
      await this.deps.manager.createConnection(
        connectionId,
        async () => {
          const resolved = await this.deps.resolveConnectConfig({ kind: 'transient', config });
          debugLogs = resolved.debugLogs;
          const existingDebug = resolved.config.debug;
          return {
            ...resolved,
            config: {
              ...resolved.config,
              readyTimeout: resolved.config.readyTimeout ?? 10_000,
              debug: (information: string) => {
                existingDebug?.(information);
                debugLogs.push(information);
              },
            },
          };
        },
        { ephemeral: true }
      );
      result = { success: true, latency: this.now() - startedAt, debugLogs };
    } catch (error) {
      result = {
        success: false,
        error: error instanceof Error ? error.message : String(error),
        debugLogs,
      };
    } finally {
      await this.deps.manager.dropConnection(connectionId).catch((error: unknown) => {
        this.deps.log.warn('SshService.testConnection: error dropping transient connection', {
          connectionId,
          error: String(error),
        });
      });
    }

    this.deps.telemetry.capture('ssh_connection_attempted', { success: result.success });
    return result;
  }

  /** Intentionally close a connection and stop auto-reconnect. */
  async disconnect(connectionId: string): Promise<void> {
    await this.updateShouldConnect(connectionId, false);
    await this.dropConnection(connectionId);
  }

  async dropConnection(connectionId: string): Promise<void> {
    if (this.deps.manager.getConnectionState(connectionId) !== 'disconnected') {
      await this.deps.manager.dropConnection(connectionId);
    }
  }

  removeRuntimeState(connectionId: string): void {
    this.deps.runtime.remove(connectionId);
  }

  /** Ensure a connection is established (no-op if already connected). */
  async connect(connectionId: string): Promise<ConnectionState> {
    await this.updateShouldConnect(connectionId, true);
    return await this.connectFromPersistedConfig(connectionId);
  }

  /**
   * Ensure a connection for background consumers without changing user intent.
   * Explicitly disconnected machines remain disconnected until a user connects again.
   */
  async ensureConnected(connectionId: string): Promise<ConnectionState> {
    const row = await this.loadConnectionRow(connectionId);
    if (row.shouldConnect === 0) return 'disconnected';
    return await this.connectFromPersistedConfig(connectionId);
  }

  private async connectFromPersistedConfig(connectionId: string): Promise<ConnectionState> {
    await this.deps.manager.createConnection(connectionId, async () => {
      const row = await this.loadConnectionRow(connectionId);
      return await this.deps.resolveConnectConfig({ kind: 'persisted', row });
    });
    return this.deps.manager.getConnectionState(connectionId);
  }

  private async loadConnectionRow(connectionId: string): Promise<SshConnectionRow> {
    const [row] = await this.deps.db
      .select()
      .from(sshConnectionsTable)
      .where(eq(sshConnectionsTable.id, connectionId))
      .limit(1);
    if (!row) throw new SshConnectionNotFoundError(connectionId);
    return row;
  }

  private async updateShouldConnect(connectionId: string, shouldConnect: boolean): Promise<void> {
    await this.deps.db
      .update(sshConnectionsTable)
      .set({
        shouldConnect: shouldConnect ? 1 : 0,
        updatedAt: new Date(this.now()).toISOString(),
      })
      .where(eq(sshConnectionsTable.id, connectionId));
  }
}
