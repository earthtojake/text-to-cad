import { beforeEach, describe, expect, it, vi } from 'vitest';
import { restoreTask } from './restoreTask';

const mocks = vi.hoisted(() => ({
  returning: vi.fn(),
  updateSet: vi.fn(),
  updateWhere: vi.fn(),
}));

const db = {
  update: () => ({
    set: mocks.updateSet,
  }),
} as never;

describe('restoreTask', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.updateSet.mockReturnValue({ where: mocks.updateWhere });
    mocks.updateWhere.mockReturnValue({ returning: mocks.returning });
  });

  it('restores by clearing archivedAt without changing lifecycle status', async () => {
    mocks.returning.mockResolvedValueOnce([
      {
        id: 'task-1',
        projectId: 'project-1',
        name: 'Task 1',
        status: 'done',
        linkedIssue: null,
        archivedAt: null,
        lastInteractedAt: null,
        createdAt: '2026-01-01T00:00:00.000Z',
        updatedAt: '2026-01-02T00:00:00.000Z',
        statusChangedAt: '2026-01-01T00:00:00.000Z',
        isPinned: 0,
        workspaceId: 'workspace-1',
        type: 'task',
        automationRunId: null,
      },
    ]);

    const task = await restoreTask(db, 'task-1');

    expect(mocks.updateSet).toHaveBeenCalledWith(
      expect.objectContaining({
        archivedAt: null,
        updatedAt: expect.anything(),
      })
    );
    const updatePayload = mocks.updateSet.mock.calls[0]?.[0];
    expect(updatePayload).not.toHaveProperty('status');
    expect(updatePayload).not.toHaveProperty('statusChangedAt');
    expect(task?.status).toBe('done');
    expect(task?.archivedAt).toBeUndefined();
  });
});
