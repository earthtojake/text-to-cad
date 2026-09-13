import { mkdtemp, mkdir, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { ROOT_RELATIVE_PATH } from '#primitives/path/api';
import { DefaultFileSearchExclusions } from '../../exclusions';
import { relativePath as relative } from '../../testing/paths';
import { NodePathScanner } from './scanner';

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true }))
  );
});

describe('NodePathScanner', () => {
  it('scans files and directories while pruning excluded segments', async () => {
    const root = await createRoot();
    await mkdir(path.join(root, 'src'));
    await writeFile(path.join(root, 'src', 'index.ts'), 'export {}');
    await mkdir(path.join(root, 'node_modules', 'pkg'), { recursive: true });
    await writeFile(path.join(root, 'node_modules', 'pkg', 'index.js'), 'module.exports = {}');

    expect(await scan(root, ROOT_RELATIVE_PATH)).toEqual([
      { path: 'src', kind: 'directory' },
      { path: 'src/index.ts', kind: 'file' },
    ]);
    expect(await scan(root, relative('src'))).toEqual([
      { path: 'src', kind: 'directory' },
      { path: 'src/index.ts', kind: 'file' },
    ]);
  });

  it.skipIf(process.platform === 'win32')(
    'indexes safe symlink targets but never traverses directory symlinks or root escapes',
    async () => {
      const parent = await createRoot();
      const root = path.join(parent, 'workspace');
      const outside = path.join(parent, 'outside');
      await mkdir(path.join(root, 'real-dir'), { recursive: true });
      await mkdir(outside);
      await writeFile(path.join(root, 'real-file.ts'), 'inside');
      await writeFile(path.join(root, 'real-dir', 'child.ts'), 'inside');
      await writeFile(path.join(outside, 'secret.ts'), 'outside');
      await symlink('real-file.ts', path.join(root, 'file-link'));
      await symlink('real-dir', path.join(root, 'directory-link'));
      await symlink(outside, path.join(root, 'outside-link'));
      await symlink('missing', path.join(root, 'broken-link'));

      expect(await scan(root, ROOT_RELATIVE_PATH)).toEqual([
        { path: 'directory-link', kind: 'directory' },
        { path: 'file-link', kind: 'file' },
        { path: 'real-dir', kind: 'directory' },
        { path: 'real-dir/child.ts', kind: 'file' },
        { path: 'real-file.ts', kind: 'file' },
      ]);
      expect(await scan(root, relative('directory-link/child.ts'))).toEqual([]);
    }
  );
});

async function createRoot(): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), 'emdash-file-search-scanner-'));
  temporaryDirectories.push(root);
  return realpath(root);
}

async function scan(root: string, relativeRoot: ReturnType<typeof relative>) {
  const entries = [];
  const scanner = new NodePathScanner();
  for await (const entry of scanner.scan(root, relativeRoot, {
    signal: new AbortController().signal,
    exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
  })) {
    entries.push(entry);
  }
  return entries.sort((left, right) => left.path.localeCompare(right.path));
}
