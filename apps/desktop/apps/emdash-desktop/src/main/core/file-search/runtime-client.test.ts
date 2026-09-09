import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { err, ok } from '@emdash/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hostPathFromNative, portablePath } from '@core/primitives/desktop-runtime/api';
import { createFileSearchRuntime, searchFileSearchRoot } from './runtime-client';

const mocks = vi.hoisted(() => ({
  client: vi.fn(),
  registerRoot: vi.fn(),
  searchPaths: vi.fn(),
  unregisterRoot: vi.fn(),
  getSearchExclusions: vi.fn(),
  warn: vi.fn(),
}));

vi.mock('@main/lib/logger', () => ({
  log: { warn: mocks.warn },
}));

describe('file-search runtime client', () => {
  const runtime = createFileSearchRuntime({ client: mocks.client } as never, {
    getSearchExclusions: mocks.getSearchExclusions,
  });

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getSearchExclusions.mockResolvedValue(['node_modules']);
    mocks.client.mockResolvedValue(
      ok({
        fileSearch: {
          registerRoot: mocks.registerRoot,
          searchPaths: mocks.searchPaths,
          unregisterRoot: mocks.unregisterRoot,
        },
      })
    );
    mocks.registerRoot.mockResolvedValue(ok());
    mocks.unregisterRoot.mockResolvedValue(ok());
  });

  it('registers and unregisters structured workspace roots', async () => {
    const root = hostPathFromNative('/repo');

    await runtime.registerRoot(root, LOCAL_HOST_REF);
    await runtime.unregisterRoot(root, LOCAL_HOST_REF);

    expect(mocks.registerRoot).toHaveBeenCalledWith({ root, exclusions: ['node_modules'] });
    expect(mocks.unregisterRoot).toHaveBeenCalledWith({ root });
    expect(mocks.client).toHaveBeenCalledTimes(2);
    expect(mocks.client).toHaveBeenNthCalledWith(1, LOCAL_HOST_REF);
    expect(mocks.client).toHaveBeenNthCalledWith(2, LOCAL_HOST_REF);
  });

  it('routes root registration and unregistration through the workspace host client', async () => {
    const root = hostPathFromNative('/repo');
    const remoteHost = hostRef('remote', 'machine-1');

    await runtime.registerRoot(root, remoteHost);
    await runtime.unregisterRoot(root, remoteHost);

    expect(mocks.client).toHaveBeenCalledTimes(2);
    expect(mocks.client).toHaveBeenNthCalledWith(1, remoteHost);
    expect(mocks.client).toHaveBeenNthCalledWith(2, remoteHost);
    expect(mocks.registerRoot).toHaveBeenCalledWith({ root, exclusions: ['node_modules'] });
    expect(mocks.unregisterRoot).toHaveBeenCalledWith({ root });
  });

  it('re-registers active roots when exclusions are refreshed, without an unregister step', async () => {
    const root = hostPathFromNative('/repo');
    mocks.getSearchExclusions
      .mockResolvedValueOnce(['node_modules'])
      .mockResolvedValueOnce(['dist']);

    await runtime.registerRoot(root, LOCAL_HOST_REF);
    await runtime.refreshExclusions();

    // refreshExclusions calls registerRoot only — the server handles fingerprint comparison.
    expect(mocks.unregisterRoot).not.toHaveBeenCalled();
    expect(mocks.registerRoot).toHaveBeenCalledTimes(2);
    expect(mocks.registerRoot).toHaveBeenNthCalledWith(1, {
      root,
      exclusions: ['node_modules'],
    });
    expect(mocks.registerRoot).toHaveBeenNthCalledWith(2, { root, exclusions: ['dist'] });
  });

  it('searches only files and preserves absolute desktop file identities', async () => {
    const root = hostPathFromNative('/repo');
    mocks.searchPaths.mockResolvedValue(
      ok({ hits: [{ path: portablePath('src/index.ts'), kind: 'file' as const }] })
    );

    const client = { searchPaths: mocks.searchPaths } as never;
    await expect(searchFileSearchRoot(client, root, 'index', 500)).resolves.toEqual([
      { path: '/repo/src/index.ts', filename: 'index.ts' },
    ]);
    expect(mocks.searchPaths).toHaveBeenCalledWith({
      root,
      query: 'index',
      kinds: ['file'],
      limit: 200,
    });
  });

  it('quietly omits file hits while a root index is still being built', async () => {
    const root = hostPathFromNative('/repo');
    mocks.searchPaths.mockResolvedValue(
      err({ type: 'index-not-ready', root, message: 'still building' })
    );

    await expect(
      searchFileSearchRoot({ searchPaths: mocks.searchPaths } as never, root, 'index')
    ).resolves.toEqual([]);
    expect(mocks.warn).not.toHaveBeenCalled();
  });

  it('logs operational search failures and returns no file hits', async () => {
    const root = hostPathFromNative('/repo');
    mocks.searchPaths.mockResolvedValue(err({ type: 'io', root, message: 'database failed' }));

    await expect(
      searchFileSearchRoot({ searchPaths: mocks.searchPaths } as never, root, 'index')
    ).resolves.toEqual([]);
    expect(mocks.warn).toHaveBeenCalledOnce();
  });
});
