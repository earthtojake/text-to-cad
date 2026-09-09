import { describe, expect, it, vi } from 'vitest';
import {
  createUnprovisionedTask,
  createUnregisteredTask,
} from '@core/features/tasks/api/browser/stores/task-store';
import type { TaskComposition } from '@core/features/workbench/api/browser/task-composition';
import type { UnregisteredTaskData } from '@core/primitives/task-state/browser/task-state';
import type { Task } from '@core/primitives/tasks/api';
import { TaskCompositionHandle } from './task-composition-handle';

vi.mock('@core/manifests/browser/task-scoped-stores', () => ({
  taskStoreContributions: [],
}));

type FakeComposition = {
  activate: ReturnType<typeof vi.fn>;
  dispose: ReturnType<typeof vi.fn>;
  space: { ready: Promise<void> };
};

function makeTask(workspaceId: string): Task {
  return {
    id: 'task-1',
    projectId: 'project-1',
    name: 'Task 1',
    status: 'todo',
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z',
    statusChangedAt: '2026-01-01T00:00:00.000Z',
    isPinned: false,
    prs: [],
    conversations: {},
    workspaceId,
    type: 'task',
  };
}

function makeUnregisteredTask(): UnregisteredTaskData {
  return {
    id: 'task-1',
    name: 'Task 1',
    status: 'todo',
    createdAt: '2026-01-01T00:00:00.000Z',
    lastInteractedAt: '2026-01-01T00:00:00.000Z',
    statusChangedAt: '2026-01-01T00:00:00.000Z',
    isPinned: false,
    type: 'task',
  };
}

function fakeComposition(): FakeComposition {
  return {
    activate: vi.fn(),
    dispose: vi.fn(),
    space: { ready: Promise.resolve() },
  };
}

describe('TaskCompositionHandle', () => {
  it('waits for the authoritative workspace identity before creating a composition', () => {
    const task = createUnregisteredTask(makeUnregisteredTask(), 'project-1');
    const composition = fakeComposition();
    const create = vi.fn((_workspaceId: string) => composition as unknown as TaskComposition);
    const handle = new TaskCompositionHandle(task, create);

    expect(handle.current).toBeNull();
    expect(create).not.toHaveBeenCalled();

    task.transitionToUnprovisioned(makeTask('workspace-1'), 'provision');

    expect(create).toHaveBeenCalledOnce();
    expect(create).toHaveBeenCalledWith('workspace-1');
    expect(handle.current).toBe(composition);
  });

  it('replaces the composition when the authoritative workspace identity changes', () => {
    const task = createUnprovisionedTask(makeTask('workspace-1'));
    const first = fakeComposition();
    const second = fakeComposition();
    const create = vi
      .fn<(workspaceId: string) => TaskComposition>()
      .mockReturnValueOnce(first as unknown as TaskComposition)
      .mockReturnValueOnce(second as unknown as TaskComposition);
    const handle = new TaskCompositionHandle(task, create);

    task.transitionToProvisioned(makeTask('workspace-1'), '/tmp/workspace-2', 'workspace-2');

    expect(first.dispose).toHaveBeenCalledOnce();
    expect(create).toHaveBeenNthCalledWith(2, 'workspace-2');
    expect(handle.current).toBe(second);
  });

  it('activates a composition created after the handle was activated', () => {
    const task = createUnregisteredTask(makeUnregisteredTask(), 'project-1');
    const composition = fakeComposition();
    const handle = new TaskCompositionHandle(task, () => composition as unknown as TaskComposition);

    handle.activate();
    task.transitionToUnprovisioned(makeTask('workspace-1'), 'provision');

    expect(composition.activate).toHaveBeenCalledOnce();
  });

  it('disposes its composition and stops observing the task', () => {
    const task = createUnprovisionedTask(makeTask('workspace-1'));
    const composition = fakeComposition();
    const create = vi.fn(() => composition as unknown as TaskComposition);
    const handle = new TaskCompositionHandle(task, create);

    handle.dispose();
    task.transitionToProvisioned(makeTask('workspace-1'), '/tmp/workspace-2', 'workspace-2');

    expect(composition.dispose).toHaveBeenCalledOnce();
    expect(create).toHaveBeenCalledOnce();
    expect(handle.current).toBeNull();
  });
});
