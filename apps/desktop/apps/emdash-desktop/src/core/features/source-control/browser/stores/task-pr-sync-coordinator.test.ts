import { observable, runInAction } from 'mobx';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { GitRepositoryStore } from '@core/features/source-control/api/browser/stores/git-repository-store';
import { getTaskPrAssociationStore } from '@core/features/source-control/api/browser/stores/task-source-control-selectors';
import type { TaskManagerStore } from '@core/features/tasks/api/browser/stores/task-manager';
import { createUnprovisionedTask } from '@core/features/tasks/api/browser/stores/task-store';
import type { Task } from '@core/primitives/tasks/api';
import { TaskPrSyncCoordinator } from './task-pr-sync-coordinator';

const mocks = vi.hoisted(() => ({
  getPullRequestsRuntimeClient: vi.fn(() => new Promise<never>(() => {})),
}));

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

vi.mock('@core/services/pull-requests/api/client', () => ({
  getPullRequestsRuntimeClient: mocks.getPullRequestsRuntimeClient,
}));

const coordinators: TaskPrSyncCoordinator[] = [];

afterEach(() => {
  for (const coordinator of coordinators) coordinator.dispose();
  coordinators.length = 0;
  mocks.getPullRequestsRuntimeClient.mockClear();
});

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
    prs: [
      {
        url: 'https://github.com/emdash/emdash/pull/42',
        repositoryUrl: 'https://github.com/emdash/emdash',
      } as Task['prs'][number],
    ],
    conversations: {},
    workspaceId: 'workspace-1',
    type: 'task',
    ...overrides,
  };
}

function makeTasks(task: Task): TaskManagerStore {
  const store = createUnprovisionedTask(task);
  getTaskPrAssociationStore(store).setAssociation(task.prs, { kind: 'unknown' });
  return { tasks: observable.map([[task.id, store]]) } as unknown as TaskManagerStore;
}

function prs(tasks: TaskManagerStore, taskId: string): readonly Task['prs'][number][] | undefined {
  const store = tasks.tasks.get(taskId);
  return store ? getTaskPrAssociationStore(store).pullRequests : undefined;
}

function makeRepository(input: {
  repositoryUrl: string | null;
  observation:
    | { kind: 'unavailable' }
    | {
        kind: 'fresh';
        value:
          | { success: false; error: { type: 'no_remote' } }
          | {
              success: true;
              data: {
                provider: 'github';
                host: string;
                repositoryUrl: string;
                nameWithOwner: string;
                capabilities: { pullRequests: boolean; issues: boolean };
              };
            };
        observedAt: number;
      };
}): GitRepositoryStore {
  return observable({
    pullRequestRepositoryUrl: input.repositoryUrl,
    providerRepositoryObservation: input.observation,
  }) as unknown as GitRepositoryStore;
}

function start(tasks: TaskManagerStore, repository: GitRepositoryStore): TaskPrSyncCoordinator {
  const coordinator = new TaskPrSyncCoordinator(tasks, repository);
  coordinators.push(coordinator);
  return coordinator;
}

describe('TaskPrSyncCoordinator association preservation', () => {
  it('preserves the last-known PR when the base remote is removed', () => {
    const task = makeTask();
    const tasks = makeTasks(task);
    const repository = makeRepository({
      repositoryUrl: null,
      observation: {
        kind: 'fresh',
        value: { success: false, error: { type: 'no_remote' } },
        observedAt: 1,
      },
    });

    start(tasks, repository);

    expect(prs(tasks, task.id)).toHaveLength(1);
  });

  it('preserves a stale PR while repository capability is transiently unavailable', () => {
    const task = makeTask();
    const tasks = makeTasks(task);
    const repository = makeRepository({
      repositoryUrl: null,
      observation: { kind: 'unavailable' },
    });

    start(tasks, repository);

    expect(prs(tasks, task.id)).toHaveLength(1);
  });

  it('preserves the last-known PR when a task no longer has a durable workspace', () => {
    const task = makeTask({ workspaceId: undefined });
    const tasks = makeTasks(task);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    const repository = makeRepository({
      repositoryUrl,
      observation: {
        kind: 'fresh',
        value: {
          success: true,
          data: {
            provider: 'github',
            host: 'github.com',
            repositoryUrl,
            nameWithOwner: 'emdash/emdash',
            capabilities: { pullRequests: true, issues: true },
          },
        },
        observedAt: 1,
      },
    });

    start(tasks, repository);

    expect(prs(tasks, task.id)).toHaveLength(1);
  });

  it('preserves a stale PR during a transient input-less read of an associated workspace', () => {
    const task = makeTask();
    const tasks = makeTasks(task);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    const repository = makeRepository({
      repositoryUrl,
      observation: {
        kind: 'fresh',
        value: {
          success: true,
          data: {
            provider: 'github',
            host: 'github.com',
            repositoryUrl,
            nameWithOwner: 'emdash/emdash',
            capabilities: { pullRequests: true, issues: true },
          },
        },
        observedAt: 1,
      },
    });

    start(tasks, repository);

    expect(prs(tasks, task.id)).toHaveLength(1);
  });

  it('preserves the last-known PR when the associated workspace checkout is missing', () => {
    const task = makeTask();
    const tasks = makeTasks(task);
    runInAction(() => {
      const store = tasks.tasks.get(task.id);
      if (store) {
        store.workspaceObservedStatus = 'missing';
        store.workspaceObservedPr = {
          branch: 'feature',
          prBreadcrumb: 'https://github.com/emdash/emdash/pull/42',
          upstream: null,
          headOid: null,
          ahead: null,
          behind: null,
        };
      }
    });
    const repositoryUrl = 'https://github.com/emdash/emdash';
    const repository = makeRepository({
      repositoryUrl,
      observation: {
        kind: 'fresh',
        value: {
          success: true,
          data: {
            provider: 'github',
            host: 'github.com',
            repositoryUrl,
            nameWithOwner: 'emdash/emdash',
            capabilities: { pullRequests: true, issues: true },
          },
        },
        observedAt: 1,
      },
    });

    start(tasks, repository);

    expect(prs(tasks, task.id)).toHaveLength(1);
  });

  it('preserves the last-known PR while a changed repository is being resolved', () => {
    const task = makeTask({
      prs: [
        {
          url: 'https://github.com/emdash/old-repository/pull/42',
          repositoryUrl: 'https://github.com/emdash/old-repository',
        } as Task['prs'][number],
      ],
    });
    const tasks = makeTasks(task);
    const repositoryUrl = 'https://github.com/emdash/new-repository';
    const repository = makeRepository({
      repositoryUrl,
      observation: {
        kind: 'fresh',
        value: {
          success: true,
          data: {
            provider: 'github',
            host: 'github.com',
            repositoryUrl,
            nameWithOwner: 'emdash/new-repository',
            capabilities: { pullRequests: true, issues: true },
          },
        },
        observedAt: 1,
      },
    });

    start(tasks, repository);

    expect(prs(tasks, task.id)).toHaveLength(1);
  });

  it('preserves the last-known PR when an available remote is removed', () => {
    const task = makeTask();
    const tasks = makeTasks(task);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    const repository = makeRepository({
      repositoryUrl,
      observation: {
        kind: 'fresh',
        value: {
          success: true,
          data: {
            provider: 'github',
            host: 'github.com',
            repositoryUrl,
            nameWithOwner: 'emdash/emdash',
            capabilities: { pullRequests: true, issues: true },
          },
        },
        observedAt: 1,
      },
    });
    start(tasks, repository);

    runInAction(() => {
      const mutableRepository = repository as unknown as {
        pullRequestRepositoryUrl: string | null;
        providerRepositoryObservation: {
          kind: 'fresh';
          value: { success: false; error: { type: 'no_remote' } };
          observedAt: number;
        };
      };
      mutableRepository.pullRequestRepositoryUrl = null;
      mutableRepository.providerRepositoryObservation = {
        kind: 'fresh',
        value: { success: false, error: { type: 'no_remote' } },
        observedAt: 2,
      };
    });

    expect(prs(tasks, task.id)).toHaveLength(1);
  });
});
