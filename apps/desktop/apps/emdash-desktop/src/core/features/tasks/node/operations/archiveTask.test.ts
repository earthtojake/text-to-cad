import { beforeEach, describe, expect, it, vi } from 'vitest';
import { archiveTask } from './archiveTask';

const mocks = vi.hoisted(() => ({
  capture: vi.fn(),
  forceRemoveTask: vi.fn(),
  selectLimit: vi.fn(),
  teardownTask: vi.fn(),
  updateSet: vi.fn(),
  updateWhere: vi.fn(),
}));

const db = {
  select: () => ({
    from: () => ({
      where: () => ({
        limit: mocks.selectLimit,
      }),
    }),
  }),
  update: () => ({
    set: mocks.updateSet,
  }),
} as never;
const taskSessions = {
  forceRemoveTask: mocks.forceRemoveTask,
  teardownTask: mocks.teardownTask,
};

describe('archiveTask', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.updateSet.mockReturnValue({ where: mocks.updateWhere });
    mocks.updateWhere.mockResolvedValue(undefined);
  });

  it('archives by reaping the runtime without deleting workspace assets', async () => {
    mocks.selectLimit.mockResolvedValueOnce([
      {
        id: 'task-1',
        workspaceId: 'workspace-1',
        status: 'done',
      },
    ]);
    mocks.teardownTask.mockResolvedValue({ success: true });

    await archiveTask(db, taskSessions, 'project-1', 'task-1', { capture: mocks.capture });

    expect(mocks.updateSet).toHaveBeenCalledWith(
      expect.objectContaining({
        archivedAt: expect.anything(),
        updatedAt: expect.anything(),
      })
    );
    const updatePayload = mocks.updateSet.mock.calls[0]?.[0];
    expect(updatePayload).not.toHaveProperty('status');
    expect(updatePayload).not.toHaveProperty('statusChangedAt');

    expect(mocks.teardownTask).toHaveBeenCalledWith('task-1', 'archive');
    expect(mocks.capture).toHaveBeenCalledWith('task_archived', {
      project_id: 'project-1',
      task_id: 'task-1',
    });
    expect(mocks.selectLimit).toHaveBeenCalledTimes(1);
  });

  it('force-removes retained lifecycle ownership when teardown fails and archive continues', async () => {
    mocks.selectLimit.mockResolvedValueOnce([
      {
        id: 'task-1',
        workspaceId: 'workspace-1',
        status: 'done',
      },
    ]);
    mocks.teardownTask.mockResolvedValue({
      success: false,
      error: { message: 'teardown failed' },
    });

    await archiveTask(db, taskSessions, 'project-1', 'task-1', { capture: mocks.capture });

    expect(mocks.forceRemoveTask).toHaveBeenCalledWith(
      'task-1',
      'archiveTask continued after teardown failure'
    );
  });
});
