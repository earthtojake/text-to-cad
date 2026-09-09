import { mkdtemp, mkdir, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { hostPath as absolute, relativePath as relative } from '../testing/paths';
import { resolveContentScope } from './content-scope';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe('resolveContentScope', () => {
  it('resolves a portable relative directory beneath the canonical root', async () => {
    const rootPath = await createRoot();
    await mkdir(path.join(rootPath, 'src', 'nested'), { recursive: true });
    const root = absolute(rootPath);

    await expect(
      resolveContentScope(rootPath, { root, query: 'term', under: relative('src/nested') })
    ).resolves.toEqual({
      success: true,
      data: { rootPath, searchPath: path.join(rootPath, 'src', 'nested') },
    });
  });

  it('returns typed availability errors for missing and non-directory scopes', async () => {
    const rootPath = await createRoot();
    await writeFile(path.join(rootPath, 'file.txt'), 'content');
    const root = absolute(rootPath);

    await expect(
      resolveContentScope(rootPath, { root, query: 'term', under: relative('missing') })
    ).resolves.toMatchObject({
      success: false,
      error: { type: 'root-unavailable', reason: 'not-found' },
    });
    await expect(
      resolveContentScope(rootPath, { root, query: 'term', under: relative('file.txt') })
    ).resolves.toMatchObject({
      success: false,
      error: { type: 'root-unavailable', reason: 'not-a-directory' },
    });
  });

  it.skipIf(process.platform === 'win32')(
    'rejects directory symlinks even when their target remains inside the root',
    async () => {
      const rootPath = await createRoot();
      await mkdir(path.join(rootPath, 'real'));
      await symlink('real', path.join(rootPath, 'alias'));
      const root = absolute(rootPath);

      await expect(
        resolveContentScope(rootPath, { root, query: 'term', under: relative('alias') })
      ).resolves.toMatchObject({
        success: false,
        error: { type: 'root-unavailable', reason: 'invalid-path' },
      });
    }
  );
});

async function createRoot(): Promise<string> {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'emdash-content-scope-'));
  roots.push(directory);
  return realpath(directory);
}
