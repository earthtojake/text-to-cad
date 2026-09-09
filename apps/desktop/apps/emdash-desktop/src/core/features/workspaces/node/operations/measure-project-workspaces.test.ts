import { ok } from '@emdash/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectWorkspaceRow } from '@core/primitives/workspaces/api';
import { measureProjectWorkspaces } from './measure-project-workspaces';

const mocks = vi.hoisted(() => ({
  getProject: vi.fn(),
  list: vi.fn(),
}));

vi.mock('./list-project-workspaces', () => ({
  getProjectWorkspaceProject: mocks.getProject,
  listProjectWorkspaces: mocks.list,
  mapWithConcurrency: async <T, U>(
    items: readonly T[],
    _limit: number,
    mapItem: (item: T) => Promise<U>
  ) => Promise.all(items.map(mapItem)),
  projectWorkspaceHost: (project: { sshConnectionId: string | null }) => ({
    type: project.sshConnectionId ? 'remote' : 'local',
    id: project.sshConnectionId ?? 'local',
  }),
}));

describe('measureProjectWorkspaces', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('measures a remote workspace through its host runtime', async () => {
    const row: ProjectWorkspaceRow = {
      kind: 'root',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      path: '/srv/repo',
      tasks: [],
      usage: null,
      gitStats: null,
      pathState: 'measured',
      canCleanArtifacts: false,
      canDelete: false,
      hasActiveSessions: false,
      pendingRemoval: false,
      errors: [],
    };
    mocks.getProject.mockResolvedValue({
      id: 'project-1',
      path: '/srv/repo',
      workspaceProvider: 'ssh',
      sshConnectionId: 'ssh-1',
      repositoryWorkspaceId: 'workspace-1',
    });
    mocks.list.mockResolvedValue({
      scannedAt: new Date().toISOString(),
      projectId: 'project-1',
      rows: [row],
      totalBytes: 0,
      artifactBytes: 0,
      warnings: [],
    });
    const measureUsage = vi.fn(async () =>
      ok({
        totalBytes: 1_024,
        artifactBytes: 256,
        errors: [],
      })
    );
    const client = vi.fn(async () =>
      ok({
        workspaceRegistry: { measureUsage },
      } as never)
    );

    const result = await measureProjectWorkspaces(
      {
        db: {} as never,
        runtimes: { client },
        taskSessions: { getTask: vi.fn() },
      },
      { projectId: 'project-1', paths: ['/srv/repo'] }
    );

    expect(client).toHaveBeenCalledWith({ type: 'remote', id: 'ssh-1' });
    expect(measureUsage).toHaveBeenCalledWith({ workspaceId: 'workspace-1' });
    expect(result.results).toEqual([
      {
        path: '/srv/repo',
        success: true,
        usage: { totalBytes: 1_024, artifactBytes: 256, errors: [] },
      },
    ]);
  });

  it('fails a row without a registered workspace id instead of calling the host', async () => {
    const row: ProjectWorkspaceRow = {
      kind: 'candidate',
      projectId: 'project-1',
      workspaceId: null,
      path: '/srv/unregistered',
      tasks: [],
      usage: null,
      gitStats: null,
      pathState: 'measured',
      canCleanArtifacts: false,
      canDelete: false,
      hasActiveSessions: false,
      pendingRemoval: false,
      errors: [],
    };
    mocks.getProject.mockResolvedValue({
      id: 'project-1',
      path: '/srv/repo',
      workspaceProvider: 'local',
      sshConnectionId: null,
      repositoryWorkspaceId: 'workspace-1',
    });
    mocks.list.mockResolvedValue({
      scannedAt: new Date().toISOString(),
      projectId: 'project-1',
      rows: [row],
      totalBytes: 0,
      artifactBytes: 0,
      warnings: [],
    });
    const measureUsage = vi.fn();
    const client = vi.fn(async () =>
      ok({
        workspaceRegistry: { measureUsage },
      } as never)
    );

    const result = await measureProjectWorkspaces(
      {
        db: {} as never,
        runtimes: { client },
        taskSessions: { getTask: vi.fn() },
      },
      { projectId: 'project-1', paths: ['/srv/unregistered'] }
    );

    expect(measureUsage).not.toHaveBeenCalled();
    expect(result.results).toEqual([
      {
        path: '/srv/unregistered',
        success: false,
        message: 'Workspace is not registered.',
      },
    ]);
  });
});
