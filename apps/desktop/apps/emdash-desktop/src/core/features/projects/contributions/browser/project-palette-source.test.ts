import { describe, expect, it, vi } from 'vitest';
import type { ProjectStore } from '@core/features/projects/api/browser/stores/project';
import type { SearchClient } from '@core/features/search/api/client';
import {
  getIdleProjectPaletteEntities,
  searchProjectPaletteEntities,
} from './project-palette-source';

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  asAvailableProject: (store: ProjectStore) =>
    store.context?.kind === 'available' ? store.context.context : undefined,
  getProjectManagerStore: () => {
    throw new Error('Project manager should be injected by this test');
  },
}));

function projectStore(id: string, contextAvailable = true): ProjectStore {
  const data = {
    type: 'local' as const,
    id,
    name: `Project ${id}`,
    path: `/repos/${id}`,
    baseRef: null,
    repositoryWorkspaceId: null,
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z',
  };
  return {
    name: data.name,
    context: contextAvailable
      ? {
          kind: 'available',
          context: {
            project: data,
            host: {
              state: {
                kind: 'degraded',
                situation: 'offline',
                recovery: 'manual',
              },
            },
          },
        }
      : { kind: 'hydrating', project: data },
  } as ProjectStore;
}

describe('project palette source', () => {
  it('requests one-character candidates from the kind-filtered project source', async () => {
    const project = {
      kind: 'project' as const,
      id: 'project-1',
      projectId: null,
      taskId: null,
      title: 'Emdash',
      subtitle: '/repos/emdash',
      score: 0,
    };
    const searchPaletteEntities = vi.fn(async () => [project]);
    const getClient = vi.fn(
      async () => ({ searchPaletteEntities }) as Pick<SearchClient, 'searchPaletteEntities'>
    );

    await expect(
      searchProjectPaletteEntities(
        { query: 'e', context: { projectId: 'project-active' } },
        getClient
      )
    ).resolves.toEqual([project]);
    expect(searchPaletteEntities).toHaveBeenCalledWith({
      kind: 'project',
      query: 'e',
      context: { projectId: 'project-active' },
      limit: 50,
    });
  });

  it('returns available Projects for idle contexts while Host access is degraded', () => {
    const projects = [
      projectStore('current'),
      projectStore('one'),
      projectStore('context-unavailable', false),
      projectStore('two'),
      projectStore('three'),
      projectStore('four'),
      projectStore('five'),
      projectStore('six'),
    ];

    expect(
      getIdleProjectPaletteEntities({ projectId: 'current' }, projects).map(
        ({ id, title, subtitle }) => ({ id, title, subtitle })
      )
    ).toEqual([
      { id: 'one', title: 'Project one', subtitle: '' },
      { id: 'two', title: 'Project two', subtitle: '' },
      { id: 'three', title: 'Project three', subtitle: '' },
      { id: 'four', title: 'Project four', subtitle: '' },
      { id: 'five', title: 'Project five', subtitle: '' },
    ]);
    expect(getIdleProjectPaletteEntities({ taskId: 'task-1' }, projects)).toEqual([]);
  });
});
