import { mkdtemp, mkdir, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { hostPath as absolute } from '../testing/paths';
import { NodeFileSearchRootResolver } from './root-identity';

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true }))
  );
});

describe('NodeFileSearchRootResolver', () => {
  it('returns one canonical Wire and native identity for a directory', async () => {
    const rootPath = await createRoot();
    const resolver = new NodeFileSearchRootResolver();
    const root = absolute(rootPath);

    expect(await resolver.resolve(root)).toEqual({
      success: true,
      data: {
        rootKey: resolver.comparisonKey(root),
        rootPath: await realpath(rootPath),
      },
    });
  });

  it('distinguishes missing roots and files from directories', async () => {
    const rootPath = await createRoot();
    const filePath = path.join(rootPath, 'file.txt');
    await writeFile(filePath, 'content');
    const resolver = new NodeFileSearchRootResolver();

    expect(await resolver.resolve(absolute(path.join(rootPath, 'missing')))).toMatchObject({
      success: false,
      error: { type: 'root-unavailable', reason: 'not-found' },
    });
    expect(await resolver.resolve(absolute(filePath))).toMatchObject({
      success: false,
      error: { type: 'root-unavailable', reason: 'not-a-directory' },
    });
  });

  it.skipIf(process.platform === 'win32')(
    'rejects a symlink alias instead of creating a second durable root identity',
    async () => {
      const parent = await createRoot();
      const target = path.join(parent, 'target');
      const alias = path.join(parent, 'alias');
      await mkdir(target);
      await symlink(target, alias);
      const resolver = new NodeFileSearchRootResolver();
      const aliasRoot = absolute(alias);
      const resolved = await resolver.resolve(aliasRoot);
      expect(resolved).toMatchObject({
        success: false,
        error: { type: 'root-unavailable', reason: 'invalid-path' },
      });
    }
  );
});

async function createRoot(): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), 'emdash-file-search-root-'));
  temporaryDirectories.push(root);
  return realpath(root);
}
