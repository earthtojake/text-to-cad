import { ok } from '@emdash/shared';
import { cell } from '@emdash/wire/state';
import { expose } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import { runInAction } from 'mobx';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  ProjectHostAccess,
  ProjectHostAccessState,
} from '@core/features/projects/api/browser/stores/project-context';
import { projectViewDef } from '@core/features/projects/contributions/views';
import { getTaskPrAssociationStore } from '@core/features/source-control/api/browser/stores/task-source-control-selectors';
import { tasksWireContract } from '@core/features/tasks/api';
import { TaskManagerStore } from '@core/features/tasks/api/browser/stores/task-manager';
import { createUnprovisionedTask } from '@core/features/tasks/api/browser/stores/task-store';
import type { Task, TaskListData, TaskStatsData } from '@core/primitives/tasks/api';

const mocks = vi.hoisted(() => ({
  archiveMutation: vi.fn(),
  deleteBySubject: vi.fn(),
  deleteTasks: vi.fn(),
  getProjectManagerStore: vi.fn(),
  getTasks: vi.fn(),
  invalidateSubject: vi.fn(),
  navigate: vi.fn(),
  teardownTask: vi.fn(),
}));

let taskListState: ReturnType<typeof cell<TaskListData>>;
let taskStatsState: ReturnType<typeof cell<TaskStatsData>>;
let wire: ReturnType<typeof createTaskWire> | undefined;
let hostState: ProjectHostAccessState;

vi.mock('@core/manifests/browser/task-persistent-stores', async () => {
  const { sourceControlPersistentTaskStoreContributions } =
    await import('@core/features/source-control/contributions/browser/task-stores');
  return {
    taskPersistentStoreContributions: sourceControlPersistentTaskStoreContributions.filter(
      (contribution) => contribution.token.id === 'source-control.task-pr-association'
    ),
  };
});

vi.mock('@core/manifests/browser/task-scoped-stores', () => ({
  taskStoreContributions: [],
}));

vi.mock('@core/features/conversations/browser/acp/acp-chat-store', () => ({
  AcpChatStore: class {
    conversationId = '';
    dispose() {}
    bootstrap() {}
  },
}));

vi.mock('@core/features/conversations/browser/acp/acp-chat-panel', () => ({
  AcpChatPanel: () => null,
}));

vi.mock('@core/features/tasks/api/browser/client', () => ({
  getTasksWireClient: async () => wire!.client,
}));

vi.mock('@core/primitives/mementos/browser', () => ({
  getMementoClient: () => ({
    deleteBySubject: mocks.deleteBySubject,
    reportError: vi.fn(),
  }),
}));

vi.mock('@core/primitives/navigation/browser/navigation-selectors', () => ({
  getNavigation: () => ({
    currentRef: {
      viewId: 'task',
      params: { projectId: 'project-1', taskId: 'task-1' },
    },
    invalidateSubject: mocks.invalidateSubject,
    navigate: mocks.navigate,
  }),
}));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  getProjectManagerStore: mocks.getProjectManagerStore,
  getProjectSshConnectionId: vi.fn(),
}));

vi.mock('@emdash/ui/react/primitives', () => ({
  toast: Object.assign(vi.fn(), { error: vi.fn() }),
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

function makeTaskManager(): TaskManagerStore {
  const host = {
    get state() {
      return hostState;
    },
    get liveAction() {
      return hostState.kind === 'ready'
        ? ({ kind: 'enabled' } as const)
        : ({ kind: 'disabled', state: hostState } as const);
    },
    observe<T>(
      observation: { kind: 'never-observed' } | { kind: 'observed'; value: T; observedAt: number }
    ) {
      if (observation.kind === 'never-observed') return { kind: 'unavailable' } as const;
      return hostState.kind === 'ready'
        ? ({ kind: 'fresh', value: observation.value, observedAt: observation.observedAt } as const)
        : ({
            kind: 'stale',
            value: observation.value,
            observedAt: observation.observedAt,
          } as const);
    },
    requireLive: () =>
      hostState.kind === 'ready'
        ? ok()
        : {
            success: false as const,
            error: { type: 'attachment-unavailable' as const, host: {} as never, phase: 'waiting' },
          },
    recover: vi.fn(),
  } satisfies ProjectHostAccess;
  return new TaskManagerStore(
    'project-1',
    {
      pageData: { invalidate: vi.fn() },
    } as never,
    host
  );
}

function createTaskWire() {
  const taskListProvider = expose(
    tasksWireContract.taskList,
    { list: taskListState },
    {
      mutations: {
        async archive(context) {
          mocks.archiveMutation(context.input);
          const revision = taskListState.update(
            (previous) => ({
              tasks: previous.tasks.map((task) =>
                task.id === context.input.taskId
                  ? { ...task, archivedAt: '2026-01-02T00:00:00.000Z' }
                  : task
              ),
            }),
            { mutationIds: [context.mutationId] }
          );
          await context.observed('list', revision);
          return ok<void>();
        },
      },
    }
  );
  const taskStatsProvider = expose(tasksWireContract.taskStats, { stats: taskStatsState });
  return createTestWire(tasksWireContract, {
    createTask: vi.fn(),
    getDeletePreflight: vi.fn(),
    deleteTask: vi.fn(),
    deleteTasks: (input: { projectId: string; taskIds: string[]; options?: unknown }) =>
      mocks.deleteTasks(input),
    teardownTask: mocks.teardownTask,
    generateTaskName: vi.fn(async () => 'Task'),
    taskList: taskListProvider,
    taskStats: taskStatsProvider,
    delete: vi.fn(),
  } as never);
}

describe('TaskManagerStore lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    taskListState = cell({ tasks: [] });
    taskStatsState = cell({ byWorkspaceId: {}, observedAt: null });
    hostState = { kind: 'ready', hostGeneration: 1 };
    wire = createTaskWire();
    mocks.deleteBySubject.mockResolvedValue(undefined);
    mocks.deleteTasks.mockResolvedValue(undefined);
    mocks.getTasks.mockResolvedValue([]);
    mocks.getProjectManagerStore.mockReturnValue({ projects: new Map() });
  });

  afterEach(async () => {
    await wire?.dispose();
    wire = undefined;
  });

  it('archives without owning conversation, terminal, or workspace stores', async () => {
    const manager = makeTaskManager();
    const task = makeTask();
    taskListState.set({ tasks: [{ ...task, workspaceId: undefined }] });
    const store = createUnprovisionedTask(task);
    store.transitionToProvisioned(task, '/tmp/workspace-1', 'workspace-1');
    manager.tasks.set(task.id, store);

    await manager.archiveTask(task.id);

    expect(mocks.archiveMutation).toHaveBeenCalledWith({ taskId: 'task-1' });
    expect(store.state).toBe('unprovisioned');
    expect(store.workspaceId).toBeNull();
    expect(mocks.navigate).toHaveBeenCalledWith(projectViewDef({ projectId: 'project-1' }));
    manager.dispose();
  });

  it('deletes tasks through the operation result without event confirmations', async () => {
    const manager = makeTaskManager();
    runInAction(() => {
      manager.tasks.set('task-1', createUnprovisionedTask(makeTask()));
    });

    await manager.deleteTasks(['task-1']);

    expect(mocks.deleteTasks).toHaveBeenCalledWith({
      projectId: 'project-1',
      taskIds: ['task-1'],
      options: undefined,
    });
    expect(manager.tasks.has('task-1')).toBe(false);
    manager.dispose();
  });

  it('rolls back failed deletes without disposing the restored task store', async () => {
    const manager = makeTaskManager();
    const store = createUnprovisionedTask(makeTask());
    const dispose = vi.spyOn(store, 'dispose');
    mocks.deleteTasks.mockRejectedValueOnce(new Error('delete failed'));
    runInAction(() => {
      manager.tasks.set('task-1', store);
    });

    await expect(manager.deleteTasks(['task-1'])).rejects.toThrow('delete failed');

    expect(manager.tasks.get('task-1')).toBe(store);
    expect(dispose).not.toHaveBeenCalled();
    manager.dispose();
  });

  it('restores an active Task from desktop session metadata without Host access', async () => {
    const manager = makeTaskManager();
    const task = makeTask();
    taskListState.set({
      tasks: [
        {
          ...task,
          activeWorkspace: {
            workspaceId: 'workspace-1',
            path: '/tmp/workspace-1',
            sshConnectionId: 'ssh-1',
          },
        },
      ],
    });

    await manager.loadTasks();

    const store = manager.tasks.get(task.id);
    expect(store).toMatchObject({
      state: 'provisioned',
      workspaceId: 'workspace-1',
      workspacePath: '/tmp/workspace-1',
      workspaceSshConnectionId: 'ssh-1',
    });
    manager.dispose();
  });

  it('refreshes an active Task workspace binding after an SSH relink', async () => {
    const manager = makeTaskManager();
    const task = makeTask();
    taskListState.set({
      tasks: [
        {
          ...task,
          activeWorkspace: {
            workspaceId: 'workspace-1',
            path: '/tmp/workspace-1',
            sshConnectionId: 'ssh-1',
          },
        },
      ],
    });
    await manager.loadTasks();
    const store = manager.tasks.get(task.id);

    taskListState.set({
      tasks: [
        {
          ...task,
          activeWorkspace: {
            workspaceId: 'workspace-1',
            path: '/tmp/workspace-1',
            sshConnectionId: 'ssh-2',
          },
        },
      ],
    });

    await vi.waitFor(() => expect(store?.workspaceSshConnectionId).toBe('ssh-2'));
    expect(manager.tasks.get(task.id)).toBe(store);
    expect(store).toMatchObject({
      state: 'provisioned',
      workspaceId: 'workspace-1',
      workspacePath: '/tmp/workspace-1',
    });
    manager.dispose();
  });

  it('keeps observed Task stats as stale while Host access is unavailable', async () => {
    const manager = makeTaskManager();
    taskListState.set({ tasks: [makeTask()] });
    taskStatsState.set({
      byWorkspaceId: {
        'workspace-1': { linesAdded: 7, linesDeleted: 2 },
      },
      observedAt: 1_786_000_000_000,
    });
    await manager.loadTasks();
    await vi.waitFor(() => expect(manager.taskStatsObservation.kind).toBe('fresh'));
    const store = manager.tasks.get('task-1');

    hostState = {
      kind: 'degraded',
      situation: 'offline',
      recovery: 'automatic',
    };

    expect(manager.taskStatsObservation).toEqual({
      kind: 'stale',
      value: expect.objectContaining({
        byWorkspaceId: {
          'workspace-1': { linesAdded: 7, linesDeleted: 2 },
        },
      }),
      observedAt: 1_786_000_000_000,
    });
    expect(manager.tasks.get('task-1')).toBe(store);
    expect(store?.data).toMatchObject({
      workspaceGit: { linesAdded: 7, linesDeleted: 2 },
    });
    manager.dispose();
  });

  it('keeps renderer-derived PR state out of task-list payloads', async () => {
    const manager = makeTaskManager();
    const task = makeTask();
    const { prs: _prs, workspaceGit: _workspaceGit, ...taskRow } = task;
    taskListState.set({ tasks: [taskRow] });
    await manager.loadTasks();
    const store = manager.tasks.get(task.id)!;
    const association = getTaskPrAssociationStore(store);
    association.setAssociation(
      [{ url: 'https://github.com/emdash/emdash/pull/42' } as Task['prs'][number]],
      { kind: 'unknown' }
    );

    taskListState.set({ tasks: [{ ...taskRow, name: 'Task 1 renamed elsewhere' }] });

    await vi.waitFor(() => expect(store.data.name).toBe('Task 1 renamed elsewhere'));
    expect('prs' in store.data).toBe(false);
    expect(association.pullRequests).toHaveLength(1);
    manager.dispose();
  });

  it('removes the durable workspace without introducing PR state into task data', async () => {
    const manager = makeTaskManager();
    const task = makeTask();
    const { prs: _prs, workspaceGit: _workspaceGit, ...taskRow } = task;
    taskListState.set({ tasks: [taskRow] });
    await manager.loadTasks();
    const store = manager.tasks.get(task.id)!;

    const { workspaceId: _workspaceId, ...rowWithoutWorkspace } = taskRow;
    taskListState.set({ tasks: [rowWithoutWorkspace] });

    await vi.waitFor(() => expect((store.data as Task).workspaceId).toBeUndefined());
    expect('prs' in store.data).toBe(false);
    manager.dispose();
  });

  it('reports never-observed Task stats as unavailable', async () => {
    const manager = makeTaskManager();
    taskListState.set({ tasks: [makeTask()] });
    taskStatsState.set({ byWorkspaceId: {}, observedAt: null });

    await manager.loadTasks();

    expect(manager.taskStatsObservation).toEqual({ kind: 'unavailable' });
    manager.dispose();
  });

  it('does not provision a Task while live Project access is unavailable', async () => {
    const manager = makeTaskManager();
    const task = createUnprovisionedTask(makeTask());
    manager.tasks.set('task-1', task);
    hostState = {
      kind: 'degraded',
      situation: 'offline',
      recovery: 'automatic',
    };

    await manager.provisionTask('task-1');

    expect(task).toMatchObject({ state: 'unprovisioned', phase: 'idle' });
    manager.dispose();
  });

  it('provisions a known restored Task without waiting for task-list reconciliation', async () => {
    const manager = makeTaskManager();
    const task = createUnprovisionedTask(makeTask());
    manager.tasks.set('task-1', task);
    const loadTasks = vi
      .spyOn(manager, 'loadTasks')
      .mockReturnValue(new Promise<void>(() => undefined));
    const internal = manager as unknown as {
      _doProvision(taskId: string): Promise<void>;
    };
    const doProvision = vi.spyOn(internal, '_doProvision').mockResolvedValue(undefined);

    await manager.provisionTask('task-1');

    expect(loadTasks).not.toHaveBeenCalled();
    expect(doProvision).toHaveBeenCalledWith('task-1');
    manager.dispose();
  });

  it('does not archive an active Task when its teardown cannot reach the Project', async () => {
    const manager = makeTaskManager();
    const task = makeTask();
    const store = createUnprovisionedTask(task);
    store.transitionToProvisioned(task, '/tmp/workspace-1', 'workspace-1');
    manager.tasks.set(task.id, store);
    hostState = {
      kind: 'degraded',
      situation: 'offline',
      recovery: 'automatic',
    };

    await manager.archiveTask(task.id);

    expect(store.state).toBe('provisioned');
    expect(mocks.archiveMutation).not.toHaveBeenCalled();
    manager.dispose();
  });
});
