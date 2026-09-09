import { describe, expect, it, vi } from 'vitest';
import type { Task } from '@core/primitives/tasks/api';
import { TaskListService } from './task-list-service';

const task: Task = {
  id: 'task-1',
  projectId: 'project-1',
  name: 'Task',
  status: 'todo',
  createdAt: '2026-08-13T00:00:00.000Z',
  updatedAt: '2026-08-13T00:00:00.000Z',
  statusChangedAt: '2026-08-13T00:00:00.000Z',
  isPinned: false,
  prs: [],
  conversations: {},
  workspaceId: 'workspace-from-task',
  type: 'task',
};

describe('TaskListService', () => {
  it('enriches an active Task from persisted session and mirror state', async () => {
    const getLive = vi.fn(() => ({
      path: '/repo/worktree',
      sshConnectionId: 'ssh-1',
    }));
    const service = new TaskListService({
      taskService: { getTasks: vi.fn(async () => [task]) } as never,
      taskSessions: {
        getTask: vi.fn(() => ({})),
        getPersistData: vi.fn(() => ({ workspaceId: 'workspace-from-session' })),
      } as never,
      workspaces: { getLive } as never,
    });

    await expect(service.load('project-1')).resolves.toEqual({
      tasks: [
        {
          id: task.id,
          projectId: task.projectId,
          name: task.name,
          status: task.status,
          createdAt: task.createdAt,
          updatedAt: task.updatedAt,
          statusChangedAt: task.statusChangedAt,
          isPinned: task.isPinned,
          conversations: task.conversations,
          workspaceId: task.workspaceId,
          type: task.type,
          activeWorkspace: {
            workspaceId: 'workspace-from-session',
            path: '/repo/worktree',
            sshConnectionId: 'ssh-1',
          },
        },
      ],
    });
    expect(getLive).toHaveBeenCalledWith('workspace-from-session');
  });

  it('does not project a workspace for an inactive Task', async () => {
    const getLive = vi.fn();
    const service = new TaskListService({
      taskService: { getTasks: vi.fn(async () => [task]) } as never,
      taskSessions: {
        getTask: vi.fn(() => undefined),
        getPersistData: vi.fn(),
      } as never,
      workspaces: { getLive } as never,
    });

    const result = await service.load('project-1');

    expect(result.tasks[0]).not.toHaveProperty('activeWorkspace');
    expect(getLive).not.toHaveBeenCalled();
  });
});
