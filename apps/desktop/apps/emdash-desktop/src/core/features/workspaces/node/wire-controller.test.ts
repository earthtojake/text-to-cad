import { ok } from '@emdash/shared';
import { describe, expect, it, vi } from 'vitest';
import { createWorkspacesWireController } from './wire-controller';

vi.mock('@core/services/app-db/node/schema', () => ({
  tasks: {},
  workspaces: {},
  conversations: {},
}));

describe('createWorkspacesWireController', () => {
  const mutations = {
    archive: vi.fn(),
    delete: vi.fn(),
  };

  it('activates a task through the provision job', async () => {
    const provisionTask = vi.fn(async () =>
      ok({
        workspaceId: 'workspace-1',
        path: '/repo/worktree',
      })
    );
    const controller = createWorkspacesWireController({
      db: {} as never,
      mutations,
      provisionTask,
      reprovisionWorkspace: vi.fn(),
    });

    await expect(
      (
        controller.impl.provision as unknown as {
          run(
            input: { workspaceId: string; taskId?: string },
            ctx: { progress: (progress: unknown) => void; signal: AbortSignal }
          ): Promise<unknown>;
        }
      ).run({ workspaceId: 'workspace-1', taskId: 'task-1' }, {
        progress: vi.fn(),
        signal: new AbortController().signal,
      } as never)
    ).resolves.toEqual(
      ok({
        workspaceId: 'workspace-1',
        path: '/repo/worktree',
      })
    );

    expect(provisionTask).toHaveBeenCalledWith('task-1', expect.any(AbortSignal));
    await controller.dispose();
  });

  it('routes reprovision variants through the reprovision dependency', async () => {
    const reprovisionWorkspace = vi.fn(async () => ok({}));
    const controller = createWorkspacesWireController({
      db: {} as never,
      mutations,
      provisionTask: vi.fn(),
      reprovisionWorkspace: reprovisionWorkspace as never,
    });

    await controller.impl.reprovision?.({ workspaceId: 'workspace-1' }, {} as never);
    expect(reprovisionWorkspace).toHaveBeenCalledWith('workspace-1');

    await controller.impl.removeAndReprovision?.({ workspaceId: 'workspace-1' }, {} as never);
    expect(reprovisionWorkspace).toHaveBeenCalledWith('workspace-1', { removeFirst: true });

    await controller.dispose();
  });

  it('delegates Host-backed mutations to the mutation service', async () => {
    const archive = vi.fn(async () => ({
      success: false as const,
      error: {
        type: 'project-unavailable',
        message: 'This action requires live Project access.',
      },
    }));
    const controller = createWorkspacesWireController({
      db: {} as never,
      mutations: { archive, delete: vi.fn() },
      provisionTask: vi.fn(),
      reprovisionWorkspace: vi.fn(),
    });

    const result = await controller.impl.archive?.(
      {
        projectId: 'project-1',
        workspaceId: 'workspace-1',
        workspacePath: '/repo/worktree',
      },
      {} as never
    );
    expect(result).toEqual({
      success: false,
      error: {
        type: 'project-unavailable',
        message: 'This action requires live Project access.',
      },
    });
    expect(archive).toHaveBeenCalledWith({
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      workspacePath: '/repo/worktree',
    });
    await controller.dispose();
  });
});
