import type { WorkspaceRecord } from '@emdash/core/runtimes/workspace-registry/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { ok } from '@emdash/shared';
import { openFixture } from '@tooling/utils/db';
import { eq } from 'drizzle-orm';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { workspaceRegistryTable as workspaces } from '@core/features/workspaces/api/node/registry';
import { projects, sshConnections, tasks } from '@core/services/app-db/node/schema';
import { updateProjectConnection } from './updateProjectConnection';

function hostRecord(id: string, path: string, parentId: string | null): WorkspaceRecord {
  return {
    id,
    kind: parentId === null ? 'repository' : 'worktree',
    path,
    parentId,
    origin: 'registered',
    gitAdminName: null,
    observedStatus: 'present',
    creation: null,
    lastCreateOutcome: null,
    lifecycle: null,
    lastRemovalAttempt: null,
    git: null,
    lastActivatedAt: null,
    createdAt: 1,
    updatedAt: 1,
    lastObservedAt: 1,
    config: null,
    runtime: null,
  };
}

describe('updateProjectConnection', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
    await fixture.db.insert(sshConnections).values([
      { id: 'ssh-old', name: 'Old', host: 'old.example', username: 'user' },
      { id: 'ssh-new', name: 'New', host: 'new.example', username: 'user' },
    ]);
    await fixture.db.insert(workspaces).values([
      {
        id: 'repository',
        type: 'project-ssh',
        kind: 'repository',
        location: 'remote',
        sshConnectionId: 'ssh-old',
        path: '/repo',
      },
      {
        id: 'worktree',
        type: 'project-ssh',
        kind: 'worktree',
        location: 'remote',
        sshConnectionId: 'ssh-old',
        parentId: 'repository',
        path: '/worktree',
      },
    ]);
    await fixture.db
      .insert(projects)
      .values({ id: 'project', name: 'Project', repositoryWorkspaceId: 'repository' });
    await fixture.db.insert(tasks).values({
      id: 'task',
      projectId: 'project',
      name: 'Task',
      status: 'in_progress',
      workspaceId: 'worktree',
    });
  });

  afterEach(() => fixture.close());

  it('asks the destination Host to confirm every id before retracking the mirror', async () => {
    const createWorkspace = vi.fn(async (input: { workspaceId: string; path: string }) =>
      ok(
        hostRecord(
          input.workspaceId,
          input.path,
          input.workspaceId === 'worktree' ? 'repository' : null
        )
      )
    );
    const runtimes = {
      client: vi.fn(async () => ok({ workspaceRegistry: { createWorkspace } })),
    } as unknown as Pick<RuntimeBroker, 'client'>;
    const invalidate = vi.fn(async () => undefined);

    await updateProjectConnection(fixture.db, runtimes, { invalidate }, 'project', 'ssh-new');

    expect(createWorkspace.mock.calls.map(([input]) => input.workspaceId)).toEqual([
      'repository',
      'worktree',
    ]);
    expect(
      fixture.db
        .select()
        .from(workspaces)
        .orderBy(workspaces.id)
        .all()
        .map((row) => ({
          id: row.id,
          sshConnectionId: row.sshConnectionId,
        }))
    ).toEqual([
      { id: 'repository', sshConnectionId: 'ssh-new' },
      { id: 'worktree', sshConnectionId: 'ssh-new' },
    ]);
    expect(invalidate).toHaveBeenCalledWith('project', 'relink');
  });

  it('leaves the desktop unchanged when the destination path has another canonical id', async () => {
    const createWorkspace = vi.fn(async (input: { workspaceId: string; path: string }) =>
      ok(hostRecord(`canonical-${input.workspaceId}`, input.path, null))
    );
    const runtimes = {
      client: vi.fn(async () => ok({ workspaceRegistry: { createWorkspace } })),
    } as unknown as Pick<RuntimeBroker, 'client'>;
    const invalidate = vi.fn(async () => undefined);

    await expect(
      updateProjectConnection(fixture.db, runtimes, { invalidate }, 'project', 'ssh-new')
    ).rejects.toThrow("belongs to Workspace 'canonical-repository'");

    expect(
      fixture.db.select().from(workspaces).where(eq(workspaces.id, 'repository')).get()
        ?.sshConnectionId
    ).toBe('ssh-old');
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('recovers rows whose deleted SSH connection left their Host identity incomplete', async () => {
    fixture.db.update(workspaces).set({ sshConnectionId: null }).run();
    const createWorkspace = vi.fn(async (input: { workspaceId: string; path: string }) =>
      ok(
        hostRecord(
          input.workspaceId,
          input.path,
          input.workspaceId === 'worktree' ? 'repository' : null
        )
      )
    );
    const runtimes = {
      client: vi.fn(async () => ok({ workspaceRegistry: { createWorkspace } })),
    } as unknown as Pick<RuntimeBroker, 'client'>;

    await updateProjectConnection(
      fixture.db,
      runtimes,
      { invalidate: vi.fn(async () => undefined) },
      'project',
      'ssh-new'
    );

    expect(
      fixture.db
        .select()
        .from(workspaces)
        .all()
        .map((row) => row.sshConnectionId)
    ).toEqual(['ssh-new', 'ssh-new']);
  });
});
