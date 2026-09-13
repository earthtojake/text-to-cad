import { describe, expect, it, vi } from 'vitest';
import type { ProjectStore } from '@core/features/projects/api/browser/stores/project';
import type { TaskStore } from '@core/features/tasks/api/browser/stores/task-store';
import { taskManagerStoreToken } from './project-store-tokens';
import { listNotificationTasks } from './task-palette-provider';

const mocks = vi.hoisted(() => ({
  getConversationManager: vi.fn(),
}));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  asAvailableProject: (store: ProjectStore) =>
    store.context?.kind === 'available' ? store.context.context : undefined,
  getProjectManagerStore: () => {
    throw new Error('Project inventory should be injected by this test');
  },
}));

vi.mock('@core/features/tasks/api/browser/task-state/task-selectors', () => ({
  getTaskStore: () => undefined,
}));

vi.mock('@core/features/conversations/api/browser/stores/conversation-registry', () => ({
  conversationRegistry: { get: mocks.getConversationManager },
}));

function task(id: string, name: string, state: TaskStore['state']): TaskStore {
  return {
    state,
    data: { id, name },
  } as TaskStore;
}

describe('task palette inventory', () => {
  it('reads durable Tasks from ProjectContext while Host access is degraded', () => {
    const tasks = new Map<string, TaskStore>([
      ['task-1', task('task-1', 'Durable task', 'unprovisioned')],
      ['task-creating', task('task-creating', 'Creating task', 'unregistered')],
    ]);
    const get = vi.fn(() => ({ tasks }));
    const project = {
      type: 'ssh' as const,
      id: 'project-1',
      name: 'Remote Project',
      path: '/repos/remote',
      connectionId: 'machine-1',
      baseRef: null,
      repositoryWorkspaceId: null,
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-01T00:00:00.000Z',
    };
    const projectStore = {
      context: {
        kind: 'available',
        context: {
          project,
          host: {
            state: {
              kind: 'degraded',
              situation: 'offline',
              recovery: 'manual',
            },
          },
          get,
        },
      },
    } as unknown as ProjectStore;
    const hydratingProjectStore = {
      context: { kind: 'hydrating', project: { ...project, id: 'project-hydrating' } },
    } as unknown as ProjectStore;
    mocks.getConversationManager.mockReturnValue({
      taskStatus: 'completed',
      conversations: new Map([
        [
          'conversation-1',
          {
            data: { id: 'conversation-1', title: 'Finished work' },
            seen: false,
            indicatorStatus: 'completed',
          },
        ],
      ]),
    });

    expect(listNotificationTasks([projectStore, hydratingProjectStore])).toEqual([
      {
        projectId: 'project-1',
        taskId: 'task-1',
        title: 'Durable task',
        status: 'completed',
        conversations: [
          {
            id: 'conversation-1',
            title: 'Finished work',
            seen: false,
            indicatorStatus: 'completed',
          },
        ],
      },
    ]);
    expect(get).toHaveBeenCalledWith(taskManagerStoreToken);
    expect(mocks.getConversationManager).toHaveBeenCalledWith('task-1');
  });
});
