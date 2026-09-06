import { openFixture } from '@tooling/utils/db';
import { eq } from 'drizzle-orm';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  createConversationRegistry,
  conversationRegistryTable as conversationRows,
} from '@core/features/conversations/api/node/registry';
import { MachinesService } from '@core/features/machines/api/node/machines-service';
import {
  createWorkspaceRegistry,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import { tombstoneWorkspaceRow } from '@core/features/workspaces/api/node/registry/workspace-tombstones';
import type { AppDb } from '@core/services/app-db/node/db';
import { projects, sshConnections, tasks } from '@core/services/app-db/node/schema';

async function insertSshConnection(db: AppDb): Promise<void> {
  await db.insert(sshConnections).values({
    id: 'ssh-1',
    name: 'Existing SSH',
    host: 'example.com',
    port: 22,
    username: 'jona',
    authType: 'agent',
    useAgent: 1,
  });
}

async function insertRemoteWorkspace(db: AppDb): Promise<void> {
  await db.insert(workspaces).values({
    id: 'workspace-root-1',
    type: 'project-ssh',
    kind: 'repository',
    location: 'remote',
    sshConnectionId: 'ssh-1',
    path: '/repo',
  });
}

describe('MachinesService', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;
  let service: MachinesService;
  const deleteAllCredentials = vi.fn();
  const dropConnection = vi.fn();
  const removeRuntimeState = vi.fn();

  beforeEach(async () => {
    fixture = await openFixture('empty');
    deleteAllCredentials.mockReset();
    dropConnection.mockReset().mockResolvedValue(undefined);
    removeRuntimeState.mockReset();
    service = new MachinesService({
      db: fixture.db,
      credentials: {
        storePassword: vi.fn(),
        storePassphrase: vi.fn(),
        deleteAllCredentials,
      },
      ssh: {
        dropConnection,
        removeRuntimeState,
      },
      log: { warn: vi.fn() },
    });
  });

  afterEach(() => {
    fixture.close();
  });

  it('rejects duplicate machine names with a user-facing error', async () => {
    await insertSshConnection(fixture.db);

    await expect(
      service.saveMachine({
        name: 'Existing SSH',
        host: 'other.example.com',
        port: 22,
        username: 'jona',
        authType: 'agent',
        useAgent: true,
      })
    ).rejects.toThrow(
      'An SSH connection named “Existing SSH” already exists. Choose a different name.'
    );
  });

  it('allows saving an existing machine without renaming it', async () => {
    await insertSshConnection(fixture.db);
    const events: unknown[] = [];
    service.on('machine:mutated', (event) => {
      events.push(event);
    });

    await expect(
      service.saveMachine({
        id: 'ssh-1',
        name: 'Existing SSH',
        host: 'example.org',
        port: 22,
        username: 'jona',
        authType: 'agent',
        useAgent: true,
      })
    ).resolves.toMatchObject({ id: 'ssh-1', name: 'Existing SSH', host: 'example.org' });
    expect(dropConnection).toHaveBeenCalledWith('ssh-1');
    expect(events).toEqual([{ type: 'saved', connectionId: 'ssh-1' }]);
  });

  it('does not drop a pooled connection when creating a new machine', async () => {
    const events: unknown[] = [];
    service.on('machine:mutated', (event) => {
      events.push(event);
    });

    const saved = await service.saveMachine({
      name: 'New SSH',
      host: 'example.org',
      port: 22,
      username: 'jona',
      authType: 'agent',
      useAgent: true,
    });

    expect(dropConnection).not.toHaveBeenCalled();
    expect(events).toEqual([{ type: 'saved', connectionId: saved.id }]);
  });

  it('deletes an unused machine even when an orphan workspace still references it', async () => {
    await insertSshConnection(fixture.db);
    await insertRemoteWorkspace(fixture.db);
    const events: unknown[] = [];
    service.on('machine:mutated', (event) => {
      events.push(event);
    });

    let credentialDeleteSawConnectionRows: number | undefined;
    deleteAllCredentials.mockImplementation(async (connectionId: string) => {
      const row = fixture.sqlite
        .prepare('SELECT COUNT(*) AS count FROM ssh_connections WHERE id = ?')
        .get(connectionId) as { count: number };
      credentialDeleteSawConnectionRows = row.count;
    });

    await service.deleteMachine('ssh-1');

    const remainingConnections = await fixture.db
      .select()
      .from(sshConnections)
      .where(eq(sshConnections.id, 'ssh-1'));
    const remainingWorkspaces = await fixture.db
      .select()
      .from(workspaces)
      .where(eq(workspaces.id, 'workspace-root-1'));

    expect(remainingConnections).toHaveLength(0);
    // Forget-host purges the host's mirror rows (ADR 0006), not just untracks them.
    expect(remainingWorkspaces).toHaveLength(0);
    expect(credentialDeleteSawConnectionRows).toBe(0);
    expect(dropConnection).toHaveBeenCalledWith('ssh-1');
    expect(deleteAllCredentials).toHaveBeenCalledWith('ssh-1');
    expect(removeRuntimeState).toHaveBeenCalledWith('ssh-1');
    expect(events).toEqual([{ type: 'deleted', connectionId: 'ssh-1' }]);
  });

  it('purges the host workspace mirror rows, pending deletion tombstones included', async () => {
    await insertSshConnection(fixture.db);
    const registry = createWorkspaceRegistry(fixture.db);
    const tombstoned = registry.recordCreationIntent({
      id: 'workspace-tombstoned',
      type: 'project-ssh',
      kind: 'worktree',
      location: 'remote',
      sshConnectionId: 'ssh-1',
      path: '/repo/.worktrees/pending',
    });
    tombstoneWorkspaceRow(fixture.db, {
      workspace: tombstoned,
      options: { deleteBranch: true, deleteConversations: false },
      createdAt: 1,
    });
    registry.recordCreationIntent({
      id: 'workspace-untracked',
      type: 'project-ssh',
      kind: 'worktree',
      location: 'remote',
      sshConnectionId: 'ssh-1',
      path: '/repo/.worktrees/gone',
    });
    registry.untrack(['workspace-untracked'], '2026-01-01T00:00:00.000Z');
    // A local row is another host's mirror — forget must not touch it.
    registry.recordCreationIntent({
      id: 'workspace-local',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/local/.worktrees/keep',
    });

    await service.deleteMachine('ssh-1');

    const remaining = await fixture.db.select({ id: workspaces.id }).from(workspaces);
    expect(remaining.map((row) => row.id)).toEqual(['workspace-local']);
  });

  it('applies the conversation mirror rules when forgetting a host', async () => {
    await insertSshConnection(fixture.db);
    // A task-linked cached record and an unlinked mirror row, both from this host. The
    // task's project must not reference the machine or deletion is refused.
    await fixture.db.insert(projects).values({ id: 'project-1', name: 'Unrelated Project' });
    await fixture.db
      .insert(tasks)
      .values({ id: 'task-1', projectId: 'project-1', name: 'Task', status: 'running' });
    const registry = createConversationRegistry(fixture.db);
    registry.register({
      id: 'conv-linked',
      projectId: 'project-1',
      taskId: 'task-1',
      title: 'Linked',
      provider: 'claude',
      type: 'acp',
      location: 'remote',
      sshConnectionId: 'ssh-1',
      isInitialConversation: true,
    });
    registry.adopt({
      id: 'conv-unlinked',
      title: 'Unlinked mirror',
      provider: 'codex',
      type: 'pty',
      location: 'remote',
      sshConnectionId: 'ssh-1',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
      observedStatus: 'present',
    });

    await service.deleteMachine('ssh-1');

    // Spec §7.3: linked records stay visible as stale observations; unlinked mirror rows
    // drop with the mirror. The host's own index is untouched — re-adding reconverges.
    const rows = await fixture.db.select().from(conversationRows);
    expect(rows.map((row) => row.id)).toEqual(['conv-linked']);
    expect(rows[0]).toMatchObject({ taskId: 'task-1', untrackedAt: null });
  });

  it('setSyncLocalSettings persists the toggle without dropping the connection', async () => {
    await insertSshConnection(fixture.db);
    const mutatedEvents: unknown[] = [];
    const syncEvents: unknown[] = [];
    service.on('machine:mutated', (event) => {
      mutatedEvents.push(event);
    });
    service.on('machine:sync-local-settings-changed', (event) => {
      syncEvents.push(event);
    });

    const updated = await service.setSyncLocalSettings('ssh-1', true);
    expect(updated).toMatchObject({ id: 'ssh-1', syncLocalSettings: true });

    const [row] = await fixture.db
      .select()
      .from(sshConnections)
      .where(eq(sshConnections.id, 'ssh-1'));
    expect(row?.metadata?.syncLocalSettings).toBe(true);

    const machines = await service.getMachines();
    expect(machines.find((machine) => machine.id === 'ssh-1')?.syncLocalSettings).toBe(true);

    // Flipping the toggle must not invalidate the pinned host connection.
    expect(dropConnection).not.toHaveBeenCalled();
    expect(mutatedEvents).toEqual([]);
    expect(syncEvents).toEqual([{ connectionId: 'ssh-1', enabled: true }]);

    await service.setSyncLocalSettings('ssh-1', false);
    const after = await service.getMachines();
    expect(after.find((machine) => machine.id === 'ssh-1')?.syncLocalSettings).toBe(false);
  });

  it('setSyncLocalSettings rejects unknown machines', async () => {
    await expect(service.setSyncLocalSettings('missing', true)).rejects.toThrow(
      'SSH connection missing not found'
    );
  });

  it('saveMachine preserves the sync toggle stored in metadata', async () => {
    await insertSshConnection(fixture.db);
    await service.setSyncLocalSettings('ssh-1', true);

    const saved = await service.saveMachine({
      id: 'ssh-1',
      name: 'Existing SSH',
      host: 'example.org',
      port: 22,
      username: 'jona',
      authType: 'agent',
      useAgent: true,
    });
    expect(saved.syncLocalSettings).toBe(true);

    const machines = await service.getMachines();
    expect(machines.find((machine) => machine.id === 'ssh-1')?.syncLocalSettings).toBe(true);
  });

  it('does not delete credentials when a project still uses the machine', async () => {
    await insertSshConnection(fixture.db);
    await insertRemoteWorkspace(fixture.db);
    await fixture.db.insert(projects).values({
      id: 'project-1',
      name: 'Blocking Project',
      repositoryWorkspaceId: 'workspace-root-1',
    });

    await expect(service.deleteMachine('ssh-1')).rejects.toThrow(
      'SSH connection is used by Blocking Project'
    );

    const remainingConnections = await fixture.db
      .select()
      .from(sshConnections)
      .where(eq(sshConnections.id, 'ssh-1'));
    expect(remainingConnections).toHaveLength(1);
    expect(dropConnection).not.toHaveBeenCalled();
    expect(deleteAllCredentials).not.toHaveBeenCalled();
    expect(removeRuntimeState).not.toHaveBeenCalled();
  });

  it('removes runtime state when credential cleanup fails after database deletion', async () => {
    await insertSshConnection(fixture.db);
    deleteAllCredentials.mockRejectedValueOnce(new Error('Keychain unavailable'));

    await expect(service.deleteMachine('ssh-1')).rejects.toThrow('Keychain unavailable');

    const remainingConnections = await fixture.db
      .select()
      .from(sshConnections)
      .where(eq(sshConnections.id, 'ssh-1'));
    expect(remainingConnections).toHaveLength(0);
    expect(removeRuntimeState).toHaveBeenCalledWith('ssh-1');
  });
});
