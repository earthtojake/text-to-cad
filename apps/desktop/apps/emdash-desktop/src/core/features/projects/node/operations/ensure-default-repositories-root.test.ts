import path from 'node:path';
import { hostRef } from '@emdash/core/primitives/host/api';
import { err, ok } from '@emdash/shared';
import { describe, expect, it, vi } from 'vitest';
import { hostPathFromNative, nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import { ensureDefaultRepositoriesRoot } from './ensure-default-repositories-root';

const remoteHost = hostRef('remote', 'ssh-1');
const repositoriesRoot = '/home/devuser/emdash/repositories';

function makeHarness(existingPaths: string[]) {
  const existing = new Set(['/', '/home', ...existingPaths]);
  const exists = vi.fn(
    async ({ path: target }: { path: Parameters<typeof nativePathFromHost>[0] }) => {
      const candidate = nativePathFromHost(target);
      return ok({ exists: existing.has(candidate) });
    }
  );
  const createDirectory = vi.fn(
    async ({ path: target }: { path: Parameters<typeof nativePathFromHost>[0] }) => {
      const candidate = nativePathFromHost(target);
      const parent = path.posix.dirname(candidate);
      if (!existing.has(parent)) return err({ type: 'not-found' as const, path: candidate });
      if (existing.has(candidate)) {
        return err({ type: 'already-exists' as const, path: candidate });
      }
      existing.add(candidate);
      return ok();
    }
  );
  const placement = {
    resolveRepositoriesRoot: vi.fn(async () => ok(repositoriesRoot)),
  };
  const runtimes = {
    client: vi.fn(async () =>
      ok({
        files: {
          fs: { exists, createDirectory },
        },
      })
    ),
  };

  return {
    dependencies: { placement, runtimes } as never,
    exists,
    createDirectory,
  };
}

describe('ensureDefaultRepositoriesRoot', () => {
  it('returns an existing repositories root without creating directories', async () => {
    const { dependencies, createDirectory } = makeHarness([
      '/home/devuser',
      '/home/devuser/emdash',
      repositoriesRoot,
    ]);

    await expect(ensureDefaultRepositoriesRoot(dependencies, remoteHost)).resolves.toEqual({
      success: true,
      data: repositoriesRoot,
    });
    expect(createDirectory).not.toHaveBeenCalled();
  });

  it('creates one missing repositories-root level', async () => {
    const { dependencies, createDirectory } = makeHarness([
      '/home/devuser',
      '/home/devuser/emdash',
    ]);

    await expect(ensureDefaultRepositoriesRoot(dependencies, remoteHost)).resolves.toEqual({
      success: true,
      data: repositoriesRoot,
    });
    expect(createDirectory).toHaveBeenCalledOnce();
    expect(createDirectory).toHaveBeenCalledWith({
      path: hostPathFromNative(repositoriesRoot),
    });
  });

  it('creates two missing levels from the nearest existing ancestor', async () => {
    const { dependencies, createDirectory } = makeHarness(['/home/devuser']);

    await expect(ensureDefaultRepositoriesRoot(dependencies, remoteHost)).resolves.toEqual({
      success: true,
      data: repositoriesRoot,
    });
    expect(createDirectory.mock.calls).toEqual([
      [{ path: hostPathFromNative('/home/devuser/emdash') }],
      [{ path: hostPathFromNative(repositoriesRoot) }],
    ]);
  });
});
