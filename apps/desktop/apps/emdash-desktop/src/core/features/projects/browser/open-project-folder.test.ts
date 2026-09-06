import { describe, expect, it, vi } from 'vitest';
import { openProjectFolder, type OpenProjectFolderDependencies } from './open-project-folder';

function dependencies(
  result:
    | { kind: 'existing'; projectId: string }
    | {
        kind: 'creating';
        projectId: string;
        completion: Promise<{ success: true; data: undefined }>;
      }
) {
  const startProjectCreation = vi.fn(async () => result);
  const hydrateProjectContext = vi.fn(async () => {});
  const waitUntilReady = vi.fn(async () => {});
  const deps = {
    selectDirectory: vi.fn(async () => '/Users/amy/code/bridge-project'),
    getProjectManager: () => ({ startProjectCreation, hydrateProjectContext }),
    createId: () => 'project-created',
    waitUntilReady,
  } as unknown as OpenProjectFolderDependencies;
  return { deps, startProjectCreation, hydrateProjectContext, waitUntilReady };
}

describe('openProjectFolder', () => {
  it('registers a selected folder with its basename and waits until it can host a chat', async () => {
    const flow = dependencies({
      kind: 'creating',
      projectId: 'project-created',
      completion: Promise.resolve({ success: true, data: undefined }),
    });

    await expect(openProjectFolder('existing', flow.deps)).resolves.toBe('project-created');

    expect(flow.deps.selectDirectory).toHaveBeenCalledWith('existing');
    expect(flow.startProjectCreation).toHaveBeenCalledWith(
      { type: 'local' },
      {
        mode: 'pick',
        name: 'bridge-project',
        path: '/Users/amy/code/bridge-project',
        initGitRepository: false,
      },
      { id: 'project-created' }
    );
    expect(flow.hydrateProjectContext).toHaveBeenCalledWith('project-created');
    expect(flow.waitUntilReady).toHaveBeenCalledWith('project-created');
  });

  it('reuses an already registered folder instead of making a duplicate project', async () => {
    const flow = dependencies({ kind: 'existing', projectId: 'project-existing' });

    await expect(openProjectFolder('existing', flow.deps)).resolves.toBe('project-existing');

    expect(flow.hydrateProjectContext).toHaveBeenCalledWith('project-existing');
    expect(flow.waitUntilReady).toHaveBeenCalledWith('project-existing');
  });

  it('does nothing when the native folder picker is cancelled', async () => {
    const flow = dependencies({ kind: 'existing', projectId: 'unused' });
    vi.mocked(flow.deps.selectDirectory).mockResolvedValue(undefined);

    await expect(openProjectFolder('existing', flow.deps)).resolves.toBeNull();

    expect(flow.startProjectCreation).not.toHaveBeenCalled();
    expect(flow.hydrateProjectContext).not.toHaveBeenCalled();
    expect(flow.waitUntilReady).not.toHaveBeenCalled();
  });
});
