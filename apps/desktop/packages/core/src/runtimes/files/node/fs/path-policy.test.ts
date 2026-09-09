import { mkdir, mkdtemp, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { resolveRootIdentity } from '#runtimes/files/node/allocation/identity';
import { RootPathPolicy, normalizeRelativePath } from './path-policy';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe('RootPathPolicy', () => {
  it('normalizes safe relative paths and rejects root escapes and drive paths', () => {
    expect(normalizeRelativePath('src/index.ts')).toEqual({
      success: true,
      data: 'src/index.ts',
    });
    expect(normalizeRelativePath('src/../file')).toEqual({ success: true, data: 'file' });
    expect(normalizeRelativePath('src//file')).toEqual({ success: true, data: 'src/file' });
    for (const invalid of ['/tmp/file', '../file', 'C:relative']) {
      expect(normalizeRelativePath(invalid)).toMatchObject({
        success: false,
        error: { type: 'invalid-path' },
      });
    }
    expect(normalizeRelativePath('src\\file').success).toBe(path.sep !== '\\');
  });

  it('rejects followed paths that escape through a symlink', async () => {
    const root = await makeRoot();
    const outside = await makeRoot();
    await mkdir(path.join(outside, 'target'));
    try {
      await symlink(path.join(outside, 'target'), path.join(root, 'linked'), 'dir');
    } catch {
      return;
    }

    const policy = new RootPathPolicy(root);
    await expect(policy.resolveFollowed('linked')).resolves.toMatchObject({
      success: false,
      error: { type: 'invalid-path' },
    });
    expect(policy.resolveEntry('linked')).toMatchObject({ success: true });
  });

  it('allows operating on an outside symlink but rejects entries reached through it', async () => {
    const root = await makeRoot();
    const outside = await makeRoot();
    await writeFile(path.join(outside, 'outside.txt'), 'keep');
    try {
      await symlink(outside, path.join(root, 'linked'), 'dir');
    } catch {
      return;
    }

    const policy = new RootPathPolicy(root);
    await expect(policy.resolveExistingEntry('linked')).resolves.toMatchObject({ success: true });
    await expect(policy.resolveExistingEntry('linked/outside.txt')).resolves.toMatchObject({
      success: false,
      error: { type: 'invalid-path' },
    });
  });

  it('requires an absolute workspace root', async () => {
    const incompatibleRoot =
      path.sep === '\\'
        ? { root: { kind: 'posix' as const }, segments: ['relative', 'root'] }
        : { root: { kind: 'drive' as const, driveLetter: 'C' }, segments: ['relative', 'root'] };
    await expect(resolveRootIdentity(incompatibleRoot)).resolves.toMatchObject({
      success: false,
      error: { type: 'invalid-path', path: '' },
    });
  });
});

async function makeRoot(): Promise<string> {
  const root = await realpath(await mkdtemp(path.join(tmpdir(), 'emdash-path-policy-')));
  roots.push(root);
  return root;
}
