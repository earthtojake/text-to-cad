import { mkdir, mkdtemp, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { isExpandableFileEntry } from '#runtimes/files/api';
import { RootPathPolicy } from '#runtimes/files/node/fs/path-policy';
import { relativePath } from '#runtimes/files/node/testing/paths';
import { TreeDirectoryReader } from './directory-reader';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe('TreeDirectoryReader', () => {
  it('orders directory targets first and exposes explicit symlink target kinds', async () => {
    const root = await makeRoot();
    const outside = await makeRoot();
    await mkdir(path.join(root, 'z-directory'));
    await writeFile(path.join(root, 'a.txt'), 'a');
    await writeFile(path.join(outside, 'outside.txt'), 'outside');
    try {
      await symlink('z-directory', path.join(root, 'linked-directory'), 'dir');
      await symlink(path.join(outside, 'outside.txt'), path.join(root, 'outside-file'), 'file');
      await symlink('missing', path.join(root, 'missing-link'), 'file');
    } catch {
      return;
    }

    const result = await new TreeDirectoryReader(new RootPathPolicy(root)).readChildren(
      relativePath('')
    );
    expect(result.success).toBe(true);
    if (!result.success) return;
    expect(result.data.map((entry) => entry.name)).toEqual([
      'linked-directory',
      'z-directory',
      'a.txt',
      'missing-link',
      'outside-file',
    ]);
    expect(result.data.find((entry) => entry.name === 'linked-directory')).toMatchObject({
      kind: 'symlink',
      symlinkTargetKind: 'directory',
    });
    expect(result.data.find((entry) => entry.name === 'outside-file')).toMatchObject({
      symlinkTargetKind: 'outside-root',
    });
    expect(result.data.find((entry) => entry.name === 'missing-link')).toMatchObject({
      symlinkTargetKind: 'missing',
    });
    const linked = result.data.find((entry) => entry.name === 'linked-directory');
    expect(linked && isExpandableFileEntry(linked)).toBe(true);
    expect(linked && 'expandable' in linked).toBe(false);
  });
});

async function makeRoot(): Promise<string> {
  const root = await realpath(await mkdtemp(path.join(tmpdir(), 'emdash-directory-reader-')));
  roots.push(root);
  return root;
}
