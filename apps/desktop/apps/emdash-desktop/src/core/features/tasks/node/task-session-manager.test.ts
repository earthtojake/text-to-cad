import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TaskProvider } from '@core/features/projects/api/node/project-provider';
import {
  executeTeardown,
  TaskSessionManager,
} from '@core/features/tasks/api/node/task-session-manager';

const deactivateParticipants = vi.hoisted(() => vi.fn());
const hostDeactivate = vi.hoisted(() => vi.fn(async () => ({ success: true as const })));

const dependencies = {
  db: {} as never,
  deactivateWorkspaceParticipants: deactivateParticipants,
  workspaceIdentity: {
    resolve: vi.fn(async () => ({
      workspaceId: 'workspace-1',
      projectId: 'project-1',
      host: LOCAL_HOST_REF,
      path: '/repo/task',
    })),
  },
  runtimes: {
    client: vi.fn(async () => ({
      success: true as const,
      data: { workspaceRegistry: { deactivateWorkspace: hostDeactivate } },
    })),
  },
} as never;

function makeTask(taskId = 'task-1') {
  const conversations = { detachAll: vi.fn(), destroyAll: vi.fn() };
  const task = { taskId, conversations } as unknown as TaskProvider;
  return { task, conversations };
}

describe('executeTeardown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('detaches sessions without submitting a workspace lifecycle operation', async () => {
    const { task, conversations } = makeTask();
    await executeTeardown(dependencies, task, 'workspace-1', 'detach');

    expect(conversations.detachAll).toHaveBeenCalledOnce();
    expect(conversations.destroyAll).not.toHaveBeenCalled();
    expect(deactivateParticipants).not.toHaveBeenCalled();
  });

  it('terminates sessions and deactivates desktop participants', async () => {
    const { task, conversations } = makeTask();
    await executeTeardown(dependencies, task, 'workspace-1', 'terminate');

    expect(conversations.destroyAll).toHaveBeenCalledOnce();
    expect(deactivateParticipants).not.toHaveBeenCalled();
  });

  it('reaps archive sessions while keeping workspace lifecycle out of the session plane', async () => {
    const { task, conversations } = makeTask();
    await executeTeardown(dependencies, task, 'workspace-1', 'archive');

    expect(conversations.destroyAll).toHaveBeenCalledOnce();
    expect(deactivateParticipants).not.toHaveBeenCalled();
  });

  it('deactivates workspace participants only after the final shared task stops', async () => {
    const first = makeTask('task-1');
    const second = makeTask('task-2');
    const manager = new TaskSessionManager(dependencies);
    for (const task of [first.task, second.task]) {
      await manager.registerTask(
        task.taskId,
        {
          taskProvider: task,
          persistData: { workspaceId: 'workspace-1' },
        },
        'project-1'
      );
    }

    await Promise.all([manager.teardownTask('task-1'), manager.teardownTask('task-2')]);
    expect(deactivateParticipants).toHaveBeenCalledOnce();
    expect(hostDeactivate).toHaveBeenCalledExactlyOnceWith({ workspaceId: 'workspace-1' });
  });

  it('leaves the workspace active on the host when detaching', async () => {
    const { task } = makeTask();
    const manager = new TaskSessionManager(dependencies);
    await manager.registerTask(
      task.taskId,
      { taskProvider: task, persistData: { workspaceId: 'workspace-1' } },
      'project-1'
    );

    await manager.teardownTask('task-1', 'detach');
    expect(deactivateParticipants).toHaveBeenCalledOnce();
    expect(hostDeactivate).not.toHaveBeenCalled();
  });

  it('deactivates on the host for archive teardown', async () => {
    const { task } = makeTask();
    const manager = new TaskSessionManager(dependencies);
    await manager.registerTask(
      task.taskId,
      { taskProvider: task, persistData: { workspaceId: 'workspace-1' } },
      'project-1'
    );

    await manager.teardownTask('task-1', 'archive');
    expect(hostDeactivate).toHaveBeenCalledExactlyOnceWith({ workspaceId: 'workspace-1' });
  });
});
