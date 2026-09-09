import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PaletteController, definePaletteProviderCatalog } from '@core/primitives/palette/api';
import { createFilePaletteProviderDef, filePaletteProviderDef } from './file-palette-provider';

const mocks = vi.hoisted(() => ({
  searchWorkspaceFiles: vi.fn(),
}));

vi.mock('@core/features/search/api/client', () => ({
  getSearchClient: vi.fn(async () => ({
    searchWorkspaceFiles: mocks.searchWorkspaceFiles,
  })),
}));

vi.mock('../../browser/command-palette/open-command-palette-file', () => ({
  openCommandPaletteFile: vi.fn(),
}));

vi.mock('@core/features/workspaces/api/browser/stores/workspace-registry', () => ({
  workspaceRegistry: { get: vi.fn() },
}));

const context = {
  projectId: 'project-1',
  taskId: 'task-1',
  workspaceId: 'local-workspace',
};

describe('file palette provider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.searchWorkspaceFiles.mockResolvedValue([]);
  });

  it('has no idle rows and does not search below two characters', async () => {
    const searchWorkspaceFiles = vi.fn(async () => []);
    const provider = createFilePaletteProviderDef({
      searchWorkspaceFiles,
      getWorkspacePath: () => '/repo',
    });
    const controller = new PaletteController(definePaletteProviderCatalog([provider]));

    await controller.setInput('', context);
    await controller.setInput('@files i', context);

    expect(controller.getSnapshot().results).toEqual([]);
    expect(searchWorkspaceFiles).not.toHaveBeenCalled();

    await controller.setInput('@files in', context);

    expect(controller.getSnapshot().mode?.keyword).toBe('@files');
    expect(searchWorkspaceFiles).toHaveBeenCalledOnce();
    expect(searchWorkspaceFiles).toHaveBeenCalledWith({
      workspaceId: 'local-workspace',
      query: 'in',
      limit: 20,
    });
  });

  it.each(['local-workspace', 'remote-workspace'])(
    'delegates %s queries to the existing workspace file search',
    async (workspaceId) => {
      await filePaletteProviderDef.search({
        query: 'index',
        context: { ...context, workspaceId },
      });

      expect(mocks.searchWorkspaceFiles).toHaveBeenCalledWith({
        workspaceId,
        query: 'index',
        limit: 20,
      });
    }
  );

  it('maps filename matches as primary and displays the workspace-relative path', async () => {
    const provider = createFilePaletteProviderDef({
      searchWorkspaceFiles: vi.fn(async () => [
        { path: '/repo/src/components/button.tsx', filename: 'button.tsx' },
      ]),
      getWorkspacePath: () => '/repo',
    });

    await expect(provider.search({ query: 'button.tsx', context })).resolves.toEqual([
      {
        id: '/repo/src/components/button.tsx',
        title: 'button.tsx',
        subtitle: 'src/components/button.tsx',
        path: '/repo/src/components/button.tsx',
        projectId: 'project-1',
        taskId: 'task-1',
        relevance: { band: 'exact', score: 1 },
      },
    ]);
  });

  it('maps path-only matches as secondary and omits unrelated candidates', async () => {
    const provider = createFilePaletteProviderDef({
      searchWorkspaceFiles: vi.fn(async () => [
        { path: '/repo/src/components/button.tsx', filename: 'button.tsx' },
        { path: '/repo/test/dialog.test.tsx', filename: 'dialog.test.tsx' },
      ]),
      getWorkspacePath: () => '/repo',
    });

    const matches = await provider.search({ query: 'components', context });

    expect(matches).toHaveLength(1);
    expect(matches[0]).toMatchObject({
      id: '/repo/src/components/button.tsx',
      subtitle: 'src/components/button.tsx',
      relevance: { band: 'secondary' },
    });
  });
});
