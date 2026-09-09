import { mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { ok } from '@emdash/shared';
import { afterEach, describe, expect, it } from 'vitest';
import { FilesRuntime } from '#runtimes/files/node/files-runtime';
import { runtimeRoot } from '#runtimes/files/node/testing/paths';
import type { IWatchService } from '#services/fs-watch/api';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe('FileSystemRuntime', () => {
  it('applies mutation overwrite and deletion rules', async () => {
    const root = await makeRoot();
    const runtime = new FilesRuntime({ watcher: noopWatcher(), idleTtlMs: 0 });

    try {
      await expect(
        runtime.fs.createDirectory({ path: runtimeRoot(path.join(root, 'source')) })
      ).resolves.toMatchObject({ success: true });
      await writeFile(path.join(root, 'source/file.txt'), 'one');
      await expect(
        runtime.fs.writeFile({
          path: runtimeRoot(path.join(root, 'source/file.txt')),
          content: Buffer.from('two').toString('base64'),
          encoding: 'base64',
          precondition: { kind: 'overwrite' },
        })
      ).resolves.toMatchObject({ success: true });
      await expect(readFile(path.join(root, 'source/file.txt'), 'utf8')).resolves.toBe('two');

      await expect(
        runtime.fs.delete({ path: runtimeRoot(path.join(root, 'source')) })
      ).resolves.toMatchObject({ success: false, error: { type: 'io' } });
      await expect(
        runtime.fs.delete({ path: runtimeRoot(path.join(root, 'source')), recursive: true })
      ).resolves.toMatchObject({ success: true });
    } finally {
      await runtime.dispose();
    }
  });

  it('deletes a symlink itself without following it to the target', async () => {
    const root = await makeRoot();
    const outside = await makeRoot();
    await mkdir(path.join(outside, 'nested'));
    const outsideFile = path.join(outside, 'nested/outside.txt');
    await writeFile(outsideFile, 'keep');
    try {
      await symlink(outside, path.join(root, 'linked'), 'dir');
    } catch {
      return;
    }
    const runtime = new FilesRuntime({ watcher: noopWatcher(), idleTtlMs: 0 });

    try {
      await expect(
        runtime.fs.delete({ path: runtimeRoot(path.join(root, 'linked')) })
      ).resolves.toMatchObject({ success: true });
      await expect(readFile(outsideFile, 'utf8')).resolves.toBe('keep');
    } finally {
      await runtime.dispose();
    }
  });

  it('serializes conditional writes against the same ETag', async () => {
    const root = await makeRoot();
    await writeFile(path.join(root, 'file.txt'), 'before');
    const runtime = new FilesRuntime({ watcher: noopWatcher(), idleTtlMs: 0 });

    try {
      const read = await runtime.fs.readText({
        path: runtimeRoot(path.join(root, 'file.txt')),
      });
      expect(read.success).toBe(true);
      if (!read.success) throw read.error;

      const writes = await Promise.all([
        runtime.fs.writeFile({
          path: runtimeRoot(path.join(root, 'file.txt')),
          content: 'first',
          precondition: { kind: 'etag', etag: read.data.etag },
        }),
        runtime.fs.writeFile({
          path: runtimeRoot(path.join(root, 'file.txt')),
          content: 'second',
          precondition: { kind: 'etag', etag: read.data.etag },
        }),
      ]);

      expect(writes.filter((result) => result.success)).toHaveLength(1);
      expect(writes.filter((result) => !result.success)).toEqual([
        expect.objectContaining({ error: expect.objectContaining({ type: 'etag-mismatch' }) }),
      ]);
      await expect(readFile(path.join(root, 'file.txt'), 'utf8')).resolves.toMatch(
        /^(first|second)$/u
      );
    } finally {
      await runtime.dispose();
    }
  });
});

async function makeRoot(): Promise<string> {
  const root = await realpath(await mkdtemp(path.join(tmpdir(), 'emdash-file-system-')));
  roots.push(root);
  return root;
}

function noopWatcher(): IWatchService {
  return {
    watch: () => ({ ready: async () => ok(undefined), release: async () => {} }),
    dispose: async () => {},
  };
}
