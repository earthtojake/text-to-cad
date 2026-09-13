import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getTaskPrAssociationStore } from '@core/features/source-control/api/browser/stores/task-source-control-selectors';
import {
  createUnprovisionedTask,
  createUnregisteredTask,
} from '@core/features/tasks/api/browser/stores/task-store';
import type { UnregisteredTaskData } from '@core/primitives/task-state/browser/task-state';
import type { Task } from '@core/primitives/tasks/api';

const contributionMocks = vi.hoisted(() => ({
  create: vi.fn((_context: unknown, _stores: unknown) => ({})),
  dispose: vi.fn(),
}));

vi.mock('@core/manifests/browser/task-scoped-stores', () => ({
  taskStoreContributions: [
    {
      token: { id: 'test.lifecycle' },
      create: contributionMocks.create,
      dispose: contributionMocks.dispose,
    },
  ],
}));

function makeTask(overrides: Partial<Task> = {}): Task {
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
    workspaceId: 'workspace-1',
    type: 'task',
    ...overrides,
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

describe('TaskStore provision state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('creates task contributions before the task receives its workspace identity', () => {
    const store = createUnregisteredTask(makeUnregisteredTask(), 'project-1');

    expect(contributionMocks.create).toHaveBeenCalledOnce();
    expect(contributionMocks.create.mock.calls[0]?.[0]).toMatchObject({
      projectId: 'project-1',
      taskId: 'task-1',
      task: {
        state: 'unregistered',
        data: {
          id: 'task-1',
        },
      },
    });

    store.transitionToUnprovisioned(makeTask(), 'provision');

    expect(contributionMocks.create).toHaveBeenCalledOnce();
  });

  it('creates task contributions for a registered task without a workspace', () => {
    createUnprovisionedTask(makeTask({ workspaceId: undefined }));

    expect(contributionMocks.create).toHaveBeenCalledOnce();
  });

  it('keeps renderer-derived PR data outside the registered task payload', () => {
    const store = createUnprovisionedTask(
      makeTask({
        prs: [{ url: 'https://github.com/emdash/emdash/pull/42' } as Task['prs'][number]],
      })
    );

    expect('prs' in store.data).toBe(false);
  });

  it('retains persistent PR association state when operational task stores are disposed', () => {
    const task = makeTask();
    const store = createUnprovisionedTask(task);
    const association = getTaskPrAssociationStore(store);
    association.setAssociation(
      [{ url: 'https://github.com/emdash/emdash/pull/42' } as Task['prs'][number]],
      { kind: 'unknown' }
    );

    store.transitionToDryUnprovisioned(task);

    expect(getTaskPrAssociationStore(store)).toBe(association);
    expect(association.pullRequests).toHaveLength(1);
    expect(contributionMocks.dispose).toHaveBeenCalledOnce();
  });

  it('keeps task contributions stable when the authoritative workspace identity changes', () => {
    const store = createUnprovisionedTask(makeTask());

    store.transitionToProvisioned(
      makeTask({ workspaceId: 'workspace-2' }),
      '/tmp/workspace-2',
      'workspace-2'
    );

    expect(contributionMocks.dispose).not.toHaveBeenCalled();
    expect(contributionMocks.create).toHaveBeenCalledOnce();
  });

  it('records and clears workspace handoff data without owning workspace stores', () => {
    const task = makeTask();
    const store = createUnprovisionedTask(task);

    store.transitionToProvisioned(task, '/tmp/workspace-1', 'workspace-1', 'ssh-1');
    expect(store.state).toBe('provisioned');
    expect(store.workspaceId).toBe('workspace-1');
    expect(store.workspacePath).toBe('/tmp/workspace-1');
    expect(store.workspaceSshConnectionId).toBe('ssh-1');

    store.transitionToUnprovisioned(task);
    expect(store.state).toBe('unprovisioned');
    expect(store.workspaceId).toBeNull();
    expect(store.workspacePath).toBeNull();
    expect(store.workspaceSshConnectionId).toBeUndefined();
  });

  it('refreshes a provisioned workspace binding without recreating task contributions', () => {
    const task = makeTask();
    const store = createUnprovisionedTask(task);
    store.transitionToProvisioned(task, '/tmp/workspace-1', 'workspace-1', 'ssh-1');

    store.refreshWorkspaceBinding(task, '/tmp/workspace-1-renamed', 'workspace-1', 'ssh-2');

    expect(store).toMatchObject({
      state: 'provisioned',
      workspaceId: 'workspace-1',
      workspacePath: '/tmp/workspace-1-renamed',
      workspaceSshConnectionId: 'ssh-2',
    });
    expect(contributionMocks.dispose).not.toHaveBeenCalled();
    expect(contributionMocks.create).toHaveBeenCalledOnce();
  });

  it('disposes contributed stores exactly once', () => {
    const store = createUnprovisionedTask(makeTask());

    store.dispose();
    store.dispose();

    expect(contributionMocks.dispose).toHaveBeenCalledOnce();
  });
});
