import { describe, expect, it, vi } from 'vitest';
import { PaletteController, definePaletteProviderCatalog } from '@core/primitives/palette/api';
import type { SearchItem } from '@core/primitives/search/api';
import { createProjectPaletteProvider } from './project-palette-provider';

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  asAvailableProject: () => undefined,
  getProjectManagerStore: () => {
    throw new Error('Idle project inventory should be injected by this test');
  },
}));

function project(id: string, title: string, path: string): SearchItem {
  return {
    kind: 'project',
    id,
    projectId: null,
    taskId: null,
    title,
    subtitle: path,
    score: 0,
  };
}

describe('project palette provider', () => {
  it('matches project names as primary text and paths as secondary text', async () => {
    const provider = createProjectPaletteProvider({
      search: async () => [
        project('secondary', 'Workspace', '/repos/alpha'),
        project('unmatched', 'Beta', '/repos/beta'),
        project('primary', 'Alpha', '/repos/other'),
      ],
      idle: () => [],
    });
    const controller = new PaletteController(definePaletteProviderCatalog([provider]));

    await controller.setInput('alpha', {});

    expect(
      controller
        .getSnapshot()
        .results.map(({ match }) => ({ id: match.id, band: match.relevance.band }))
    ).toEqual([
      { id: 'primary', band: 'exact' },
      { id: 'secondary', band: 'secondary' },
    ]);

    await controller.setInput('wsp', {});

    expect(
      controller
        .getSnapshot()
        .results.map(({ match }) => ({ id: match.id, band: match.relevance.band }))
    ).toEqual([{ id: 'secondary', band: 'fuzzy' }]);
  });

  it('uses active-project affinity only to break equal relevance ties', async () => {
    const tiedProvider = createProjectPaletteProvider({
      search: async () => [
        project('inactive', 'Alpha One', '/repos/one'),
        project('active', 'Alpha Two', '/repos/two'),
      ],
      idle: () => [],
    });
    const tiedController = new PaletteController(definePaletteProviderCatalog([tiedProvider]));

    await tiedController.setInput('alpha', { projectId: 'active' });

    expect(tiedController.getSnapshot().results.map(({ match }) => match.id)).toEqual([
      'active',
      'inactive',
    ]);

    const bandedProvider = createProjectPaletteProvider({
      search: async () => [
        project('active', 'My Alpha', '/repos/active'),
        project('inactive', 'Alpha App', '/repos/inactive'),
      ],
      idle: () => [],
    });
    const bandedController = new PaletteController(definePaletteProviderCatalog([bandedProvider]));

    await bandedController.setInput('alpha', { projectId: 'active' });

    expect(
      bandedController
        .getSnapshot()
        .results.map(({ match }) => ({ id: match.id, band: match.relevance.band }))
    ).toEqual([
      { id: 'inactive', band: 'prefix' },
      { id: 'active', band: 'substring' },
    ]);
  });

  it('supports one-character @projects searches with the controller cap', async () => {
    const search = vi.fn(async () =>
      Array.from({ length: 25 }, (_, index) =>
        project(`project-${index}`, `X project ${index}`, `/repos/project-${index}`)
      )
    );
    const otherSearch = vi.fn(() => []);
    const provider = createProjectPaletteProvider({ search, idle: () => [] });
    const controller = new PaletteController(
      definePaletteProviderCatalog([
        {
          kind: 'commands',
          keyword: '@commands',
          minQueryLength: 1,
          search: otherSearch,
          render: () => null,
        },
        provider,
      ])
    );

    await controller.setInput('@projects x', { projectId: 'active' });

    expect(controller.getSnapshot().mode).toEqual({
      kind: 'projects',
      keyword: '@projects',
    });
    expect(controller.getSnapshot().results).toHaveLength(20);
    expect(search).toHaveBeenCalledWith({
      query: 'x',
      context: { projectId: 'active' },
    });
    expect(otherSearch).not.toHaveBeenCalled();
  });
});
