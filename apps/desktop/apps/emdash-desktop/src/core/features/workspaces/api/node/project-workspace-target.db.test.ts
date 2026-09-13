import { hostRef } from '@emdash/core/primitives/host/api';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { projects, tasks } from '@core/services/app-db/node/schema';
import { resolveProjectWorkspaceTarget } from './project-workspace-target';
import { createWorkspaceRegistry } from './registry';

describe('resolveProjectWorkspaceTarget', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
    const registry = createWorkspaceRegistry(fixture.db);
    registry.adopt({
      id: 'repo-1',
      type: 'local',
      kind: 'repository',
      location: 'local',
      path: '/repo',
    });
    registry.adopt({
      id: 'child-1',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      parentId: 'repo-1',
      path: '/worktrees/child-1',
    });
    registry.adopt({
      id: 'foreign-1',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      parentId: 'repo-other',
      path: '/worktrees/foreign-1',
    });
    registry.adopt({
      id: 'wrong-host-1',
      type: 'project-ssh',
      kind: 'worktree',
      location: 'remote',
      parentId: 'repo-1',
      path: '/worktrees/wrong-host-1',
    });
    fixture.db
      .insert(projects)
      .values({ id: 'project-1', name: 'Project', repositoryWorkspaceId: 'repo-1' })
      .run();
  });

  afterEach(() => {
    fixture.close();
  });

  it('accepts an adopted child from the project workspace registry', async () => {
    const result = await resolveProjectWorkspaceTarget(
      fixture.db,
      { id: 'project-1', repositoryWorkspaceId: 'repo-1', host: hostRef('local', 'local') },
      'child-1'
    );

    expect(result).toMatchObject({ success: true, data: { id: 'child-1' } });
  });

  it('rejects a workspace owned by another project', async () => {
    const result = await resolveProjectWorkspaceTarget(
      fixture.db,
      { id: 'project-1', repositoryWorkspaceId: 'repo-1', host: hostRef('local', 'local') },
      'foreign-1'
    );

    expect(result).toEqual({
      success: false,
      error: {
        type: 'workspace-unavailable',
        workspaceId: 'foreign-1',
        message: 'The selected workspace does not belong to this project.',
      },
    });
  });

  it('accepts a legacy workspace linked through a project task', async () => {
    fixture.db
      .insert(tasks)
      .values({
        id: 'task-1',
        projectId: 'project-1',
        name: 'Legacy task',
        status: 'in_progress',
        workspaceId: 'foreign-1',
      })
      .run();

    const result = await resolveProjectWorkspaceTarget(
      fixture.db,
      { id: 'project-1', repositoryWorkspaceId: 'repo-1', host: hostRef('local', 'local') },
      'foreign-1'
    );

    expect(result).toMatchObject({ success: true, data: { id: 'foreign-1' } });
  });

  it('rejects a missing project workspace path', async () => {
    createWorkspaceRegistry(fixture.db).refresh('child-1', { observedStatus: 'missing' });

    const result = await resolveProjectWorkspaceTarget(
      fixture.db,
      { id: 'project-1', repositoryWorkspaceId: 'repo-1', host: hostRef('local', 'local') },
      'child-1'
    );

    expect(result).toMatchObject({
      success: false,
      error: { type: 'workspace-unavailable', workspaceId: 'child-1' },
    });
  });

  it('rejects a project workspace observed on another host', async () => {
    const result = await resolveProjectWorkspaceTarget(
      fixture.db,
      { id: 'project-1', repositoryWorkspaceId: 'repo-1', host: hostRef('local', 'local') },
      'wrong-host-1'
    );

    expect(result).toEqual({
      success: false,
      error: {
        type: 'workspace-unavailable',
        workspaceId: 'wrong-host-1',
        message: 'The selected workspace belongs to a different host.',
      },
    });
  });
});
