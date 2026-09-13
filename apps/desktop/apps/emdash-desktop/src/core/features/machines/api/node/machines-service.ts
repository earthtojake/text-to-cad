import { randomUUID } from 'node:crypto';
import { secret, type Secret } from '@emdash/shared';
import { and, eq, isNull, ne } from 'drizzle-orm';
import {
  createConversationRegistry,
  conversationRegistryTable as conversationRows,
} from '@core/features/conversations/api/node/registry';
import {
  createWorkspaceRegistry,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import { HookCore, type Hookable } from '@core/primitives/hooks/api/hookable';
import {
  mergeSshConnectionMetadata,
  sshConfigFromRow,
  type SshConfig,
  type SshConnectionMetadata,
  type SshConnectionUsage,
} from '@core/primitives/ssh/api';
import type { AppDb } from '@core/services/app-db/node/db';
import {
  projects,
  sshConnections as sshConnectionsTable,
  type SshConnectionInsert,
} from '@core/services/app-db/node/schema';
import type { SaveMachineInput } from '..';

type MachinesCredentials = {
  storePassword(connectionId: string, password: Secret<string>): Promise<void>;
  storePassphrase(connectionId: string, passphrase: Secret<string>): Promise<void>;
  deleteAllCredentials(connectionId: string): Promise<void>;
};

type MachinesSshRuntime = {
  dropConnection(connectionId: string): Promise<void>;
  removeRuntimeState(connectionId: string): void;
};

type MachinesLog = {
  warn(message: string, metadata?: Record<string, unknown>): void;
};

export interface MachinesServiceDeps {
  db: AppDb;
  credentials: MachinesCredentials;
  ssh: MachinesSshRuntime;
  log: MachinesLog;
  createId?: () => string;
  now?: () => number;
}

export type MachineMutationEvent = {
  type: 'saved' | 'deleted';
  connectionId: string;
};

export type SyncLocalSettingsChangedEvent = {
  connectionId: string;
  enabled: boolean;
};

export type MachinesServiceHooks = {
  'machine:mutated': (event: MachineMutationEvent) => void | Promise<void>;
  /**
   * The per-host "Sync local settings" toggle changed. Separate from
   * machine:mutated on purpose: flipping the toggle must not invalidate the
   * host's pinned connection.
   */
  'machine:sync-local-settings-changed': (
    event: SyncLocalSettingsChangedEvent
  ) => void | Promise<void>;
};

export class MachinesService implements Hookable<MachinesServiceHooks> {
  private readonly createId: () => string;
  private readonly now: () => number;
  private readonly hooks: HookCore<MachinesServiceHooks>;

  constructor(private readonly deps: MachinesServiceDeps) {
    this.createId = deps.createId ?? randomUUID;
    this.now = deps.now ?? Date.now;
    this.hooks = new HookCore<MachinesServiceHooks>((name, error) => {
      deps.log.warn(`MachinesService: ${String(name)} hook failed`, { error });
    });
  }

  on<K extends keyof MachinesServiceHooks>(name: K, handler: MachinesServiceHooks[K]): () => void {
    return this.hooks.on(name, handler);
  }

  async getMachines(): Promise<SshConfig[]> {
    const rows = await this.deps.db.select().from(sshConnectionsTable);
    return rows.map(sshConfigFromRow);
  }

  async getMachineUsage(): Promise<SshConnectionUsage> {
    const rows = await this.deps.db
      .select({
        id: projects.id,
        name: projects.name,
        sshConnectionId: workspaces.sshConnectionId,
      })
      .from(projects)
      .leftJoin(workspaces, eq(workspaces.id, projects.repositoryWorkspaceId))
      .where(isNull(projects.deletedAt));

    const usage: SshConnectionUsage = {};
    for (const row of rows) {
      if (!row.sshConnectionId) continue;
      usage[row.sshConnectionId] ??= [];
      usage[row.sshConnectionId].push({ id: row.id, name: row.name });
    }
    return usage;
  }

  async saveMachine(config: SaveMachineInput): Promise<SshConfig> {
    const connectionId = config.id ?? this.createId();
    const existingConnectionWithName = await this.deps.db
      .select({ id: sshConnectionsTable.id })
      .from(sshConnectionsTable)
      .where(
        config.id
          ? and(eq(sshConnectionsTable.name, config.name), ne(sshConnectionsTable.id, connectionId))
          : eq(sshConnectionsTable.name, config.name)
      )
      .limit(1);

    if (existingConnectionWithName.length > 0) {
      throw new Error(
        `An SSH connection named “${config.name}” already exists. Choose a different name.`
      );
    }

    // Wrap wire-fresh credential strings into Secret at first touch; they
    // stay wrapped through the credential service and secrets store.
    if (config.password) {
      await this.deps.credentials.storePassword(
        connectionId,
        secret(config.password, 'ssh-password')
      );
    }
    if (config.passphrase) {
      await this.deps.credentials.storePassphrase(
        connectionId,
        secret(config.passphrase, 'ssh-passphrase')
      );
    }

    const { password: _password, passphrase: _passphrase, ...dbConfig } = config;

    const existingRows =
      config.id === undefined
        ? []
        : await this.deps.db
            .select({ metadata: sshConnectionsTable.metadata })
            .from(sshConnectionsTable)
            .where(eq(sshConnectionsTable.id, connectionId))
            .limit(1);
    const existingMetadata: SshConnectionMetadata = existingRows[0]?.metadata ?? {};

    const metadataUpdate: SshConnectionMetadata = {};
    if (Object.prototype.hasOwnProperty.call(config, 'sshConfigAlias')) {
      metadataUpdate.sshConfigAlias = config.sshConfigAlias;
    }
    if (Object.prototype.hasOwnProperty.call(config, 'forwardAgent')) {
      metadataUpdate.forwardAgent = config.forwardAgent;
    }
    if (Object.prototype.hasOwnProperty.call(config, 'proxyJump')) {
      metadataUpdate.proxyJump = config.proxyJump;
    }
    const metadata = mergeSshConnectionMetadata(existingMetadata, metadataUpdate);

    const insertData: SshConnectionInsert = {
      id: connectionId,
      name: dbConfig.name,
      host: dbConfig.host,
      port: dbConfig.port,
      metadata,
      username: dbConfig.username,
      authType: dbConfig.authType,
      privateKeyPath: dbConfig.privateKeyPath ?? null,
      useAgent: dbConfig.useAgent ? 1 : 0,
    };

    await this.deps.db
      .insert(sshConnectionsTable)
      .values(insertData)
      .onConflictDoUpdate({
        target: sshConnectionsTable.id,
        set: {
          name: insertData.name,
          host: insertData.host,
          port: insertData.port,
          metadata: insertData.metadata,
          username: insertData.username,
          authType: insertData.authType,
          privateKeyPath: insertData.privateKeyPath,
          useAgent: insertData.useAgent,
          updatedAt: new Date(this.now()).toISOString(),
        },
      });

    if (existingRows.length > 0) {
      await this.deps.ssh.dropConnection(connectionId).catch((error: unknown) => {
        this.deps.log.warn('MachinesService.saveMachine: error disconnecting previous config', {
          connectionId,
          error: String(error),
        });
      });
    }
    this.hooks.callHookBackground('machine:mutated', { type: 'saved', connectionId });

    return {
      ...dbConfig,
      id: connectionId,
      sshConfigAlias: metadata.sshConfigAlias,
      forwardAgent: metadata.forwardAgent,
      proxyJump: metadata.proxyJump,
      syncLocalSettings: metadata.syncLocalSettings,
    };
  }

  async setSyncLocalSettings(id: string, enabled: boolean): Promise<SshConfig> {
    const [row] = await this.deps.db
      .select()
      .from(sshConnectionsTable)
      .where(eq(sshConnectionsTable.id, id));
    if (!row) throw new Error(`SSH connection ${id} not found`);

    const metadata: SshConnectionMetadata = {
      ...(row.metadata ?? {}),
      version: '4',
      syncLocalSettings: enabled,
    };
    await this.deps.db
      .update(sshConnectionsTable)
      .set({ metadata, updatedAt: new Date(this.now()).toISOString() })
      .where(eq(sshConnectionsTable.id, id));

    this.hooks.callHookBackground('machine:sync-local-settings-changed', {
      connectionId: id,
      enabled,
    });
    return sshConfigFromRow({ ...row, metadata });
  }

  async deleteMachine(id: string): Promise<void> {
    const referencingProjects = await this.deps.db
      .select({ name: projects.name })
      .from(projects)
      .innerJoin(workspaces, eq(workspaces.id, projects.repositoryWorkspaceId))
      .where(and(eq(workspaces.sshConnectionId, id), isNull(projects.deletedAt)));

    if (referencingProjects.length > 0) {
      const projectNames = referencingProjects.map((project) => project.name).join(', ');
      throw new Error(`SSH connection is used by ${projectNames}`);
    }

    // Forget-host cascade: purge the host's workspace mirror rows — pending deletion
    // tombstones included (ADR 0006: forget means forget). Nothing host-side is
    // touched; re-adding the host reconverges from its own registry.
    const registryIds = this.deps.db
      .select({ id: workspaces.id })
      .from(workspaces)
      .where(eq(workspaces.sshConnectionId, id))
      .all()
      .map(({ id: workspaceId }) => workspaceId);
    if (registryIds.length > 0) {
      const workspaceRegistry = createWorkspaceRegistry(this.deps.db);
      this.deps.db.transaction((tx) => {
        workspaceRegistry.untrack(registryIds, new Date(this.now()).toISOString(), undefined, tx);
        workspaceRegistry.purge(registryIds, tx);
      });
    }

    // Conversation mirror rules (spec §7.3): task-linked cached records stay visible as
    // stale observations; unlinked mirror rows drop with the mirror. The host's own index
    // is untouched — re-adding the host reconverges everything, because the client never
    // held authority.
    const unlinkedMirrorIds = this.deps.db
      .select({ id: conversationRows.id })
      .from(conversationRows)
      .where(and(eq(conversationRows.sshConnectionId, id), isNull(conversationRows.taskId)))
      .all()
      .map(({ id: conversationId }) => conversationId);
    if (unlinkedMirrorIds.length > 0) {
      const conversationRegistry = createConversationRegistry(this.deps.db);
      this.deps.db.transaction((tx) => {
        conversationRegistry.untrack(unlinkedMirrorIds, new Date(this.now()).toISOString(), tx);
        conversationRegistry.purge(unlinkedMirrorIds, tx);
      });
    }

    await this.deps.ssh.dropConnection(id).catch((error: unknown) => {
      this.deps.log.warn('MachinesService.deleteMachine: error disconnecting', {
        connectionId: id,
        error: String(error),
      });
    });
    await this.deps.db.delete(sshConnectionsTable).where(eq(sshConnectionsTable.id, id));
    try {
      await this.deps.credentials.deleteAllCredentials(id);
    } finally {
      this.deps.ssh.removeRuntimeState(id);
      this.hooks.callHookBackground('machine:mutated', {
        type: 'deleted',
        connectionId: id,
      });
    }
  }

  async renameMachine(id: string, name: string): Promise<void> {
    const [row] = await this.deps.db
      .select()
      .from(sshConnectionsTable)
      .where(eq(sshConnectionsTable.id, id));
    if (!row) throw new Error(`SSH connection ${id} not found`);
    await this.deps.db
      .update(sshConnectionsTable)
      .set({ name, updatedAt: new Date(this.now()).toISOString() })
      .where(eq(sshConnectionsTable.id, id));
  }
}
