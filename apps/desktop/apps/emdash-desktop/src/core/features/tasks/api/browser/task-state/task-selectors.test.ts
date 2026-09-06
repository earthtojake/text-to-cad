import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectStore } from '@core/features/projects/api/browser/stores/project';
import type { TaskStore } from '@core/features/tasks/api/browser/stores/task-store';
import {
  taskHostActionAvailability,
  taskViewKind,
} from '@core/features/tasks/api/browser/task-state/task-selectors';

const projectManager = {
  projects: new Map<string, ProjectStore>(),
};

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  asAvailableProject: (store: ProjectStore | undefined) =>
    store?.context?.kind === 'available' ? store.context.context : undefined,
  getProjectManagerStore: () => projectManager,
  getProjectStore: (projectId: string) => projectManager.projects.get(projectId),
}));

function projectWithContext(context: ProjectStore['context']): ProjectStore {
  return {
    state: 'registered',
    id: 'project-id',
    context,
  } as ProjectStore;
}

describe('taskViewKind Project context routing', () => {
  beforeEach(() => {
    projectManager.projects.clear();
  });

  it('waits while the desktop Project context hydrates', () => {
    projectManager.projects.set(
      'project-id',
      projectWithContext({
        kind: 'hydrating',
        project: { id: 'project-id' } as never,
      })
    );

    expect(taskViewKind(undefined, 'project-id')).toBe('project-hydrating');
  });

  it('reports only desktop context failure as a Project error', () => {
    projectManager.projects.set(
      'project-id',
      projectWithContext({
        kind: 'failed',
        project: { id: 'project-id' } as never,
        error: {
          type: 'context-initialization-failed',
          stage: 'memento',
          message: 'Memento hydration failed',
        },
      })
    );

    expect(taskViewKind(undefined, 'project-id')).toBe('project-error');
  });

  it('keeps the Task shell ready while Host access is degraded', () => {
    projectManager.projects.set(
      'project-id',
      projectWithContext({
        kind: 'available',
        context: { project: { id: 'project-id' } } as never,
      })
    );
    const task = { state: 'provisioned' } as TaskStore;

    expect(taskViewKind(task, 'project-id')).toBe('ready');
  });

  it('keeps Host-backed Task actions visible but disabled with the shared reason', () => {
    const state = {
      kind: 'degraded' as const,
      situation: 'offline' as const,
      recovery: 'automatic' as const,
    };
    projectManager.projects.set(
      'project-id',
      projectWithContext({
        kind: 'available',
        context: {
          project: { id: 'project-id' },
          host: {
            state,
            liveAction: { kind: 'disabled', state },
          },
        } as never,
      })
    );

    expect(taskHostActionAvailability('project-id')).toEqual({ kind: 'disabled' });
  });

  it('enables Host-backed Task actions when effective attachment is ready', () => {
    projectManager.projects.set(
      'project-id',
      projectWithContext({
        kind: 'available',
        context: {
          project: { id: 'project-id' },
          host: {
            state: { kind: 'ready', hostGeneration: 1 },
            liveAction: { kind: 'enabled' },
          },
        } as never,
      })
    );

    expect(taskHostActionAvailability('project-id')).toEqual({ kind: 'enabled' });
  });
});
