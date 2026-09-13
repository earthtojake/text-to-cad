import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TaskRow } from '@core/services/app-db/node/schema';
import { renameTask } from './renameTask';

const mocks = vi.hoisted(() => ({
  select: vi.fn(),
  update: vi.fn(),
}));

const db = { select: mocks.select, update: mocks.update } as never;

function makeTaskRow(values: Partial<TaskRow>): TaskRow {
  return {
    id: values.id ?? 'task-1',
    projectId: values.projectId ?? 'project-1',
    name: values.name ?? 'old-title',
    status: values.status ?? 'in_progress',
    sourceBranch: values.sourceBranch ?? null,
    taskBranch: values.taskBranch ?? null,
    linkedIssue: values.linkedIssue ?? null,
    archivedAt: values.archivedAt ?? null,
    deletedAt: values.deletedAt ?? null,
    createdAt: values.createdAt ?? '2026-05-28 12:00:00',
    updatedAt: values.updatedAt ?? '2026-05-28 12:00:00',
    lastInteractedAt: values.lastInteractedAt ?? null,
    statusChangedAt: values.statusChangedAt ?? '2026-05-28 12:00:00',
    isPinned: values.isPinned ?? 0,
    workspaceId: values.workspaceId ?? null,
    type: values.type ?? 'task',
    automationRunId: values.automationRunId ?? null,
  };
}

function mockSelectRows(rows: unknown[]) {
  const limit = vi.fn().mockResolvedValue(rows);
  const where = vi.fn(() => Object.assign(Promise.resolve(rows), { limit }));
  const from = vi.fn(() => ({ where }));
  mocks.select.mockReturnValue({ from });
  return { from, where, limit };
}

function mockUpdateRows(rows: TaskRow[]) {
  const returning = vi.fn().mockResolvedValue(rows);
  const where = vi.fn(() => ({ returning }));
  const set = vi.fn(() => ({ where }));
  mocks.update.mockReturnValue({ set });
  return { set, where, returning };
}

describe('renameTask', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renames the task name and nothing else', async () => {
    const originalRow = makeTaskRow({ name: 'old-title' });
    const updatedRow = makeTaskRow({ ...originalRow, name: 'new-title' });

    mockSelectRows([originalRow]);
    const update = mockUpdateRows([updatedRow]);

    const result = await renameTask(db, 'project-1', 'task-1', 'new-title');

    expect(result.success).toBe(true);
    if (!result.success) return;
    expect(result.data.task.name).toBe('new-title');
    expect(update.set).toHaveBeenCalledWith(expect.objectContaining({ name: 'new-title' }));
    expect(update.set).toHaveBeenCalledWith(
      expect.not.objectContaining({ taskBranch: expect.anything() })
    );
  });

  it('returns task-not-found when the task does not exist in the requested project', async () => {
    mockSelectRows([]);

    const result = await renameTask(db, 'project-1', 'missing-task', 'new-title');

    expect(result).toEqual({
      success: false,
      error: { type: 'task-not-found', taskId: 'missing-task' },
    });
    expect(mocks.update).not.toHaveBeenCalled();
  });
});
