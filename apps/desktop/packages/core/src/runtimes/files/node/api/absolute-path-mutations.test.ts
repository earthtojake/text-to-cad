import { mkdir, mkdtemp, readFile, realpath, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { ok } from '@emdash/shared';
import { client, connect, memoryTransportPair, serve } from '@emdash/wire/rpc';
import { afterEach, describe, expect, it } from 'vitest';
import { filesContract } from '#runtimes/files/api';
import { FilesRuntime, type FilesRuntimeOptions } from '#runtimes/files/node/files-runtime';
import { relativePath, runtimeRoot } from '#runtimes/files/node/testing/paths';
import type { IWatchService, WatchEvent, WatchOptions } from '#services/fs-watch/api';
import { createFilesController } from './controller';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe('files runtime fs mutations', () => {
  it('creates files and directories at absolute paths', async () => {
    const dir = await makeDir();
    const { connection, dispose } = await makeRuntime();

    try {
      await expect(
        connection.api.fs.createDirectory({
          path: runtimeRoot(path.join(dir, 'made-dir')),
        })
      ).resolves.toEqual({ success: true, data: undefined });
      await expect(stat(path.join(dir, 'made-dir'))).resolves.toMatchObject({});

      await expect(
        connection.api.fs.createFile({ path: runtimeRoot(path.join(dir, 'made.txt')) })
      ).resolves.toEqual({ success: true, data: undefined });
      await expect(readFile(path.join(dir, 'made.txt'), 'utf8')).resolves.toBe('');
      await expect(
        connection.api.fs.createFile({ path: runtimeRoot(path.join(dir, 'made.txt')) })
      ).resolves.toMatchObject({ success: false, error: { type: 'already-exists' } });
    } finally {
      await dispose();
    }
  });

  it('deletes files and directories at absolute paths', async () => {
    const dir = await makeDir();
    await writeFile(path.join(dir, 'doomed.txt'), 'bye\n');
    await mkdir(path.join(dir, 'nested/deep'), { recursive: true });
    const { connection, dispose } = await makeRuntime();

    try {
      await expect(
        connection.api.fs.delete({ path: runtimeRoot(path.join(dir, 'doomed.txt')) })
      ).resolves.toEqual({ success: true, data: undefined });
      await expect(stat(path.join(dir, 'doomed.txt'))).rejects.toMatchObject({ code: 'ENOENT' });

      await expect(
        connection.api.fs.delete({
          path: runtimeRoot(path.join(dir, 'nested')),
          recursive: true,
        })
      ).resolves.toEqual({ success: true, data: undefined });
      await expect(stat(path.join(dir, 'nested'))).rejects.toMatchObject({ code: 'ENOENT' });
    } finally {
      await dispose();
    }
  });

  it('renames, moves, and copies between absolute paths', async () => {
    const dir = await makeDir();
    await writeFile(path.join(dir, 'from.txt'), 'payload\n');
    await mkdir(path.join(dir, 'target'));
    const { connection, dispose } = await makeRuntime();

    try {
      await expect(
        connection.api.fs.rename({
          from: runtimeRoot(path.join(dir, 'from.txt')),
          to: runtimeRoot(path.join(dir, 'renamed.txt')),
        })
      ).resolves.toEqual({ success: true, data: undefined });
      await expect(readFile(path.join(dir, 'renamed.txt'), 'utf8')).resolves.toBe('payload\n');

      // Rename never changes the parent; that is what move is for.
      await expect(
        connection.api.fs.rename({
          from: runtimeRoot(path.join(dir, 'renamed.txt')),
          to: runtimeRoot(path.join(dir, 'target', 'renamed.txt')),
        })
      ).resolves.toMatchObject({ success: false, error: { type: 'invalid-path' } });

      await expect(
        connection.api.fs.move({
          from: runtimeRoot(path.join(dir, 'renamed.txt')),
          to: runtimeRoot(path.join(dir, 'target', 'moved.txt')),
        })
      ).resolves.toEqual({ success: true, data: undefined });
      await expect(stat(path.join(dir, 'renamed.txt'))).rejects.toMatchObject({ code: 'ENOENT' });
      await expect(readFile(path.join(dir, 'target', 'moved.txt'), 'utf8')).resolves.toBe(
        'payload\n'
      );

      await expect(
        connection.api.fs.copy({
          from: runtimeRoot(path.join(dir, 'target', 'moved.txt')),
          to: runtimeRoot(path.join(dir, 'copied.txt')),
        })
      ).resolves.toEqual({ success: true, data: undefined });
      await expect(readFile(path.join(dir, 'target', 'moved.txt'), 'utf8')).resolves.toBe(
        'payload\n'
      );
      await expect(readFile(path.join(dir, 'copied.txt'), 'utf8')).resolves.toBe('payload\n');
      await expect(
        connection.api.fs.copy({
          from: runtimeRoot(path.join(dir, 'target', 'moved.txt')),
          to: runtimeRoot(path.join(dir, 'copied.txt')),
        })
      ).resolves.toMatchObject({ success: false, error: { type: 'already-exists' } });
    } finally {
      await dispose();
    }
  });

  it('writes whole files with etag preconditions preserved', async () => {
    const dir = await makeDir();
    await writeFile(path.join(dir, 'guarded.txt'), 'original\n');
    const { connection, dispose } = await makeRuntime();

    try {
      const key = { path: runtimeRoot(path.join(dir, 'guarded.txt')) };
      const read = await connection.api.fs.readText(key);
      expect(read.success).toBe(true);
      if (!read.success) throw new Error('Expected readText to succeed');

      await expect(
        connection.api.fs.writeFile({
          ...key,
          content: 'updated\n',
          precondition: { kind: 'etag', etag: read.data.etag },
        })
      ).resolves.toEqual({ success: true, data: undefined });
      await expect(readFile(path.join(dir, 'guarded.txt'), 'utf8')).resolves.toBe('updated\n');

      await expect(
        connection.api.fs.writeFile({
          ...key,
          content: 'stale write\n',
          precondition: { kind: 'etag', etag: read.data.etag },
        })
      ).resolves.toMatchObject({ success: false, error: { type: 'etag-mismatch' } });
      await expect(readFile(path.join(dir, 'guarded.txt'), 'utf8')).resolves.toBe('updated\n');

      await expect(
        connection.api.fs.writeFile({
          ...key,
          content: 'forced\n',
          precondition: { kind: 'overwrite' },
        })
      ).resolves.toEqual({ success: true, data: undefined });
      await expect(readFile(path.join(dir, 'guarded.txt'), 'utf8')).resolves.toBe('forced\n');
    } finally {
      await dispose();
    }
  });

  it('uploads bytes to an absolute path', async () => {
    const dir = await makeDir();
    const { connection, dispose } = await makeRuntime();

    try {
      const target = runtimeRoot(path.join(dir, 'uploaded.bin'));
      const bytes = Buffer.from('hi');
      const upload = await connection.api.fs.upload(
        { path: target },
        {
          name: 'uploaded.bin',
          mimeType: 'text/plain',
          size: bytes.byteLength,
          source: chunks(bytes),
        }
      );
      expect(upload).toEqual({ success: true, data: { bytesWritten: 2 } });
      await expect(readFile(path.join(dir, 'uploaded.bin'), 'utf8')).resolves.toBe('hi');

      await expect(
        connection.api.fs.upload(
          { path: target },
          {
            name: 'uploaded.bin',
            mimeType: 'text/plain',
            size: 1,
            source: chunks(Buffer.from('x')),
          }
        )
      ).resolves.toMatchObject({ success: false, error: { type: 'already-exists' } });
    } finally {
      await dispose();
    }
  });

  // Spec §3.4: the runtime reflects its own stateless mutations into affected
  // live tree sessions at ack time. The watcher here is a stub that never
  // emits, so every tree update observed after a mutation ack must come from
  // the synchronous republish path.
  it('reflects fs mutations into open tree sessions at ack time without the watcher', async () => {
    const dir = await makeDir();
    await mkdir(path.join(dir, 'src'));
    await writeFile(path.join(dir, 'src/kept.ts'), 'kept\n');
    await writeFile(path.join(dir, 'src/doomed.ts'), 'doomed\n');
    const { connection, dispose } = await makeRuntime({ watcher: new SilentWatcher() });
    const key = { root: runtimeRoot(dir), sessionId: 'republish' };
    const treeEntries = async () =>
      (await connection.api.tree.model.state(key, 'tree').snapshot()).data.entries;

    try {
      for (const entryPath of ['', 'src']) {
        await expect(
          connection.api.tree.model.mutate('expand', {
            key,
            input: { path: relativePath(entryPath) },
          })
        ).resolves.toMatchObject({ success: true });
      }
      expect(await treeEntries()).toMatchObject({
        'src/kept.ts': { kind: 'file' },
        'src/doomed.ts': { kind: 'file' },
      });

      await expect(
        connection.api.fs.delete({ path: runtimeRoot(path.join(dir, 'src/doomed.ts')) })
      ).resolves.toEqual({ success: true, data: undefined });
      expect((await treeEntries())['src/doomed.ts']).toBeUndefined();

      await expect(
        connection.api.fs.createFile({ path: runtimeRoot(path.join(dir, 'src/fresh.ts')) })
      ).resolves.toEqual({ success: true, data: undefined });
      expect(await treeEntries()).toMatchObject({ 'src/fresh.ts': { kind: 'file' } });

      await expect(
        connection.api.fs.rename({
          from: runtimeRoot(path.join(dir, 'src/kept.ts')),
          to: runtimeRoot(path.join(dir, 'src/kept-renamed.ts')),
        })
      ).resolves.toEqual({ success: true, data: undefined });
      const afterRename = await treeEntries();
      expect(afterRename['src/kept.ts']).toBeUndefined();
      expect(afterRename['src/kept-renamed.ts']).toMatchObject({ kind: 'file' });
    } finally {
      await dispose();
    }
  });
});

async function* chunks(bytes: Uint8Array): AsyncIterable<Uint8Array> {
  yield bytes;
}

async function makeRuntime(options: FilesRuntimeOptions = {}) {
  const runtime = new FilesRuntime({
    watcher: options.watcher ?? new SilentWatcher(),
    idleTtlMs: 10_000,
    ...options,
  });
  const pair = memoryTransportPair();
  const controller = createFilesController(runtime);
  const stop = serve(pair.right, controller);
  return {
    connection: { api: client(filesContract, connect(pair.left)) },
    dispose: async () => {
      stop();
      controller.dispose?.();
      await runtime.dispose();
    },
  };
}

async function makeDir(): Promise<string> {
  const dir = await realpath(await mkdtemp(path.join(tmpdir(), 'emdash-files-mutations-')));
  roots.push(dir);
  return dir;
}

/** Accepts watch registrations but never reports any filesystem events. */
class SilentWatcher implements IWatchService {
  private readonly entries = new Map<
    string,
    { onEvents: (events: WatchEvent[]) => void; options: WatchOptions }
  >();

  watch(root: string, onEvents: (events: WatchEvent[]) => void, options: WatchOptions = {}) {
    this.entries.set(root, { onEvents, options });
    return {
      ready: async () => ok(undefined),
      release: async () => {
        this.entries.delete(root);
      },
    };
  }

  async dispose(): Promise<void> {
    this.entries.clear();
  }
}
