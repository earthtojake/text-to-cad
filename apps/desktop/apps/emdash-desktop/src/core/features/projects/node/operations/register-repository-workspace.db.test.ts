import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import type { WorkspaceRecord } from '@emdash/core/runtimes/workspace-registry/api';
import { openFixture } from '@tooling/utils/db';
import { eq } from 'drizzle-orm';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createWorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import { projects } from '@core/services/app-db/node/schema';
import { registerRepositoryWorkspace } from './register-repository-workspace';

function hostRecord(id: string, path: string): WorkspaceRecord {
  return {
    id,
    kind: 'repository',
    path,
    parentId: null,
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

describe('registerRepositoryWorkspace', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => fixture.close());

  it('atomically claims the Host record and inserts the Project with its canonical id', () => {
    const result = registerRepositoryWorkspace(fixture.db, {
      project: { id: 'project-1', name: 'Project', baseRef: 'main' },
      host: LOCAL_HOST_REF,
      record: hostRecord('canonical-repo', '/repo'),
    });

    expect(result).toMatchObject({
      success: true,
      data: { id: 'project-1', repositoryWorkspaceId: 'canonical-repo' },
    });
    expect(createWorkspaceRegistry(fixture.db).getLive('canonical-repo')).toMatchObject({
      kind: 'repository',
      path: '/repo',
      location: 'local',
    });
  });

  it('claims a remote canonical record under the selected Host identity', () => {
    fixture.sqlite
      .prepare(
        `INSERT INTO ssh_connections (id, name, host, username) VALUES ('ssh-1', 'box', 'box', 'dev')`
      )
      .run();
    const result = registerRepositoryWorkspace(fixture.db, {
      project: { id: 'project-remote', name: 'Remote', baseRef: null },
      host: hostRef('remote', 'ssh-1'),
      record: hostRecord('remote-repo', '/srv/repo'),
    });

    expect(result.success).toBe(true);
    expect(createWorkspaceRegistry(fixture.db).getLive('remote-repo')).toMatchObject({
      location: 'remote',
      sshConnectionId: 'ssh-1',
    });
  });

  it('refuses a competing desktop id at the canonical Host path without inserting a Project', () => {
    createWorkspaceRegistry(fixture.db).recordCreationIntent({
      id: 'desktop-legacy',
      type: 'local',
      kind: 'repository',
      location: 'local',
      path: '/repo',
    });

    const result = registerRepositoryWorkspace(fixture.db, {
      project: { id: 'project-1', name: 'Project', baseRef: null },
      host: LOCAL_HOST_REF,
      record: hostRecord('host-canonical', '/repo'),
    });

    expect(result).toMatchObject({
      success: false,
      error: {
        type: 'workspace-identity-conflict',
        incomingId: 'host-canonical',
        conflictingId: 'desktop-legacy',
      },
    });
    expect(fixture.db.select().from(projects).all()).toEqual([]);
  });

  it('refuses to bind two live Projects to one canonical Repository', () => {
    const first = registerRepositoryWorkspace(fixture.db, {
      project: { id: 'project-1', name: 'One', baseRef: null },
      host: LOCAL_HOST_REF,
      record: hostRecord('canonical-repo', '/repo'),
    });
    expect(first.success).toBe(true);

    const second = registerRepositoryWorkspace(fixture.db, {
      project: { id: 'project-2', name: 'Two', baseRef: null },
      host: LOCAL_HOST_REF,
      record: hostRecord('canonical-repo', '/repo'),
    });
    expect(second).toEqual({
      success: false,
      error: {
        type: 'project-already-linked',
        projectId: 'project-1',
        workspaceId: 'canonical-repo',
      },
    });
  });

  it('reuses the canonical Repository after the previous Project is detached', () => {
    expect(
      registerRepositoryWorkspace(fixture.db, {
        project: { id: 'project-old', name: 'Old', baseRef: null },
        host: LOCAL_HOST_REF,
        record: hostRecord('canonical-repo', '/repo'),
      }).success
    ).toBe(true);
    fixture.db
      .update(projects)
      .set({ deletedAt: '2026-01-02T00:00:00.000Z' })
      .where(eq(projects.id, 'project-old'))
      .run();

    const recreated = registerRepositoryWorkspace(fixture.db, {
      project: { id: 'project-new', name: 'New', baseRef: null },
      host: LOCAL_HOST_REF,
      record: hostRecord('canonical-repo', '/repo'),
    });

    expect(recreated).toMatchObject({
      success: true,
      data: { id: 'project-new', repositoryWorkspaceId: 'canonical-repo' },
    });
    expect(createWorkspaceRegistry(fixture.db).getLive('canonical-repo')).toMatchObject({
      id: 'canonical-repo',
      path: '/repo',
    });
  });
});
