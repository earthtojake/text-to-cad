import { err, ok } from '@emdash/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TaskService } from './task-service';

const operationMocks = vi.hoisted(() => ({
  archiveTask: vi.fn(),
  deleteTask: vi.fn(),
}));

vi.mock('../../node/operations/archiveTask', () => ({
  archiveTask: operationMocks.archiveTask,
}));

vi.mock('../../node/operations/deleteTask', () => ({
  deleteTask: operationMocks.deleteTask,
}));

function makeService() {
  const projects = {
    requireAttached: vi.fn(() =>
      err({
        type: 'attachment-unavailable' as const,
        host: { type: 'remote' as const, id: 'ssh-1' },
        phase: 'waiting' as const,
      })
    ),
  };
  const sessions = {
    getTask: vi.fn(() => ({ id: 'retained-session' })),
  };
  const db = {
    select: vi.fn(() => ({
      from: () => ({
        where: () => ({
          limit: async () => [{ projectId: 'project-1' }],
        }),
      }),
    })),
  };
  const service = new TaskService({
    db,
    projects,
    sessions,
    deletion: {},
  } as never);
  return { db, projects, service, sessions };
}

describe('TaskService offline desktop mutations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    operationMocks.deleteTask.mockResolvedValue(ok<void>());
    operationMocks.archiveTask.mockResolvedValue(undefined);
  });

  it('deletes through the desktop operation when a retained session Host is unavailable', async () => {
    const { projects, service } = makeService();

    await service.deleteTask('project-1', 'task-1', {
      deleteWorktree: false,
      deleteConversations: false,
    });

    expect(operationMocks.deleteTask).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        taskId: 'task-1',
        deleteWorktree: false,
        deleteConversations: false,
      })
    );
    expect(projects.requireAttached).not.toHaveBeenCalled();
  });

  it('archives through the desktop operation when retained-session teardown is unavailable', async () => {
    const { db, projects, service, sessions } = makeService();
    const telemetry = { capture: vi.fn() };

    await service.archiveTask('project-1', 'task-1', telemetry);

    expect(operationMocks.archiveTask).toHaveBeenCalledWith(
      db,
      sessions,
      'project-1',
      'task-1',
      telemetry
    );
    expect(projects.requireAttached).not.toHaveBeenCalled();
  });
});
