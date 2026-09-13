import { describe, expect, it, vi } from 'vitest';
import { WorkspaceMutationService } from './workspace-mutation-service';

const unavailableProjects = {
  requireAttached: () => ({
    success: false as const,
    error: {
      type: 'attachment-unavailable' as const,
      host: {} as never,
      phase: 'waiting' as const,
    },
  }),
};

describe('WorkspaceMutationService', () => {
  it('refuses archive when Project attachment is unavailable', async () => {
    const runtimeClient = vi.fn();
    const service = new WorkspaceMutationService({
      db: {} as never,
      projects: unavailableProjects,
      runtimes: { client: runtimeClient } as never,
    });

    await expect(
      service.archive({
        projectId: 'project-1',
        workspaceId: 'workspace-1',
        workspacePath: '/repo/worktree',
      })
    ).resolves.toEqual({
      success: false,
      error: {
        type: 'project-unavailable',
        message: 'This action requires live Project access.',
      },
    });
    expect(runtimeClient).not.toHaveBeenCalled();
  });

  it('reports a missing Project when no live Task owns the workspace', async () => {
    const service = new WorkspaceMutationService({
      db: {} as never,
      projects: unavailableProjects,
      runtimes: {} as never,
      projectIdForWorkspace: vi.fn(async () => undefined),
    });

    await expect(service.delete({ workspaceId: 'workspace-1' })).resolves.toEqual({
      success: false,
      error: {
        type: 'project-missing',
        message: 'The Project for this workspace was not found.',
      },
    });
  });

  it('checks the owning Project attachment before deleting', async () => {
    const runtimeClient = vi.fn();
    const service = new WorkspaceMutationService({
      db: {} as never,
      projects: unavailableProjects,
      runtimes: { client: runtimeClient } as never,
      projectIdForWorkspace: vi.fn(async () => 'project-1'),
    });

    await expect(service.delete({ workspaceId: 'workspace-1' })).resolves.toEqual({
      success: false,
      error: {
        type: 'project-unavailable',
        message: 'This action requires live Project access.',
      },
    });
    expect(runtimeClient).not.toHaveBeenCalled();
  });
});
