import { chmod, mkdir, mkdtemp, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { ok } from '@emdash/shared';
import { waitFor } from '@emdash/shared/testing';
import { client, connect, memoryTransportPair, serve, type LiveUpdate } from '@emdash/wire/rpc';
import { afterEach, describe, expect, it } from 'vitest';
import type { HostAbsolutePath } from '#primitives/path/api';
import { filesContract } from '#runtimes/files/api';
import { FilesRuntime, type FilesRuntimeOptions } from '#runtimes/files/node/files-runtime';
import { runtimeRoot } from '#runtimes/files/node/testing/paths';
import type { IWatchService, WatchEvent, WatchOptions } from '#services/fs-watch/api';
import { createFilesController } from './controller';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe('files runtime absolute-path content', () => {
  it('serves one-shot fs operations for an absolute path with no registered root', async () => {
    const dir = await makeDir();
    await writeFile(path.join(dir, 'note.txt'), 'outside any root\n');
    const { connection, dispose } = await makeRuntime();

    try {
      const fileKey = { path: runtimeRoot(path.join(dir, 'note.txt')) };
      await expect(connection.api.fs.exists(fileKey)).resolves.toEqual({
        success: true,
        data: { exists: true },
      });
      await expect(
        connection.api.fs.exists({ path: runtimeRoot(path.join(dir, 'missing.txt')) })
      ).resolves.toEqual({ success: true, data: { exists: false } });
      await expect(
        connection.api.fs.exists({ path: runtimeRoot(path.join(dir, 'no-parent', 'missing.txt')) })
      ).resolves.toEqual({ success: true, data: { exists: false } });

      await expect(connection.api.fs.realPath(fileKey)).resolves.toEqual({
        success: true,
        data: { path: runtimeRoot(path.join(dir, 'note.txt')) },
      });

      const text = await connection.api.fs.readText(fileKey);
      expect(text).toMatchObject({
        success: true,
        data: {
          content: 'outside any root\n',
          truncated: false,
          etag: expect.stringMatching(/^sha256:/u),
        },
      });

      const download = await connection.api.fs.readBytes(fileKey);
      expect(download.success).toBe(true);
      if (download.success) {
        expect(download.data.meta).toMatchObject({ name: 'note.txt', truncated: false });
        expect(Buffer.from(await download.data.bytes()).toString('utf8')).toBe(
          'outside any root\n'
        );
      }
    } finally {
      await dispose();
    }
  });

  it('serves live content with etag-preconditioned writes for an absolute path', async () => {
    const dir = await makeDir();
    await writeFile(path.join(dir, 'draft.md'), 'first\n');
    const { connection, dispose } = await makeRuntime();
    const key = { path: runtimeRoot(path.join(dir, 'draft.md')) };

    try {
      const snapshot = await connection.api.content.state(key, 'content').snapshot();
      expect(snapshot.data).toMatchObject({
        kind: 'text',
        content: 'first\n',
        etag: expect.stringMatching(/^sha256:/u),
      });
      if (snapshot.data.kind !== 'text') throw new Error('Expected text content');

      await expect(
        connection.api.content.mutate('write', {
          key,
          input: { content: 'second\n', precondition: { kind: 'etag', etag: snapshot.data.etag } },
        })
      ).resolves.toMatchObject({ success: true });
      await expect(connection.api.content.state(key, 'content').snapshot()).resolves.toMatchObject({
        data: { kind: 'text', content: 'second\n' },
      });

      await expect(
        connection.api.content.mutate('write', {
          key,
          input: {
            content: 'must not land\n',
            precondition: { kind: 'etag', etag: snapshot.data.etag },
          },
        })
      ).resolves.toMatchObject({ success: false, error: { type: 'etag-mismatch' } });
      await expect(connection.api.content.state(key, 'content').snapshot()).resolves.toMatchObject({
        data: { kind: 'text', content: 'second\n' },
      });
    } finally {
      await dispose();
    }
  });

  it('watches the parent directory and pushes per-file disk updates', async () => {
    const dir = await makeDir();
    const filePath = path.join(dir, 'watched.txt');
    await writeFile(filePath, 'on disk\n');
    const watcher = new ManualWatcher();
    const { connection, dispose } = await makeRuntime({ watcher });
    const key = { path: runtimeRoot(filePath) };

    try {
      await expect(connection.api.content.state(key, 'content').snapshot()).resolves.toMatchObject({
        data: { kind: 'text', content: 'on disk\n' },
      });
      expect(watcher.watchedRoots()).toContain(dir);
      expect(watcher.optionsFor(dir)?.ignore).toEqual(['*/**']);

      await writeFile(filePath, 'changed on disk\n');
      watcher.emit(dir, [{ kind: 'update', path: filePath }]);
      await waitFor(async () => {
        const snapshot = await connection.api.content.state(key, 'content').snapshot();
        return snapshot.data.kind === 'text' && snapshot.data.content === 'changed on disk\n';
      });

      await writeFile(path.join(dir, 'sibling.txt'), 'noise');
      watcher.emit(dir, [{ kind: 'create', path: path.join(dir, 'sibling.txt') }]);
      await expect(connection.api.content.state(key, 'content').snapshot()).resolves.toMatchObject({
        data: { kind: 'text', content: 'changed on disk\n' },
      });
    } finally {
      await dispose();
    }
  });

  it('surfaces delete as a distinguishable not-found update re-validated by stat', async () => {
    const dir = await makeDir();
    const filePath = path.join(dir, 'volatile.txt');
    await writeFile(filePath, 'one\n');
    const watcher = new ManualWatcher();
    const { connection, dispose } = await makeRuntime({ watcher });
    const key = { path: runtimeRoot(filePath) };
    const state = connection.api.content.state(key, 'content');
    let detach: (() => void) | undefined;

    try {
      await expect(state.snapshot()).resolves.toMatchObject({
        data: { kind: 'text', content: 'one\n' },
      });
      const updates: LiveUpdate[] = [];
      detach = await state.attach((update) => updates.push(update));

      // A delete event whose file was already recreated must not flap into
      // not-found: the reported state comes from a fresh stat/read of disk.
      await rm(filePath);
      await writeFile(filePath, 'two\n');
      watcher.emit(dir, [{ kind: 'delete', path: filePath }]);
      await waitFor(async () => {
        const snapshot = await state.snapshot();
        return snapshot.data.kind === 'text' && snapshot.data.content === 'two\n';
      });
      expect(JSON.stringify(updates)).not.toContain('unavailable');

      await rm(filePath);
      watcher.emit(dir, [{ kind: 'delete', path: filePath }]);
      await waitFor(async () => {
        const snapshot = await state.snapshot();
        return snapshot.data.kind === 'unavailable' && snapshot.data.code === 'not-found';
      });

      await writeFile(filePath, 'three\n');
      watcher.emit(dir, [{ kind: 'create', path: filePath }]);
      await waitFor(async () => {
        const snapshot = await state.snapshot();
        return snapshot.data.kind === 'text' && snapshot.data.content === 'three\n';
      });
    } finally {
      detach?.();
      await dispose();
    }
  });

  it('classifies binary and too-large content instead of truncating', async () => {
    const dir = await makeDir();
    await writeFile(path.join(dir, 'blob.bin'), new Uint8Array([1, 0, 2]));
    await writeFile(path.join(dir, 'big.txt'), 'far too large for the limit\n');
    const { connection, dispose } = await makeRuntime({ maxContentBytes: 8 });

    try {
      await expect(
        connection.api.content
          .state({ path: runtimeRoot(path.join(dir, 'blob.bin')) }, 'content')
          .snapshot()
      ).resolves.toMatchObject({ data: { kind: 'binary', byteSize: 3 } });
      await expect(
        connection.api.content
          .state({ path: runtimeRoot(path.join(dir, 'big.txt')) }, 'content')
          .snapshot()
      ).resolves.toMatchObject({ data: { kind: 'too-large', byteSize: 28, limit: 8 } });
    } finally {
      await dispose();
    }
  });

  it('reports missing files and permission failures through seam errors', async () => {
    const dir = await makeDir();
    await writeFile(path.join(dir, 'locked.txt'), 'secret\n');
    const { connection, dispose } = await makeRuntime();

    try {
      await expect(
        connection.api.content
          .state({ path: runtimeRoot(path.join(dir, 'absent.txt')) }, 'content')
          .snapshot()
      ).resolves.toMatchObject({
        data: { kind: 'unavailable', code: 'not-found' },
      });

      if (process.platform !== 'win32' && process.getuid?.() !== 0) {
        await chmod(path.join(dir, 'locked.txt'), 0o000);
        await expect(
          connection.api.content
            .state({ path: runtimeRoot(path.join(dir, 'locked.txt')) }, 'content')
            .snapshot()
        ).resolves.toMatchObject({
          data: { kind: 'unavailable', code: 'no-permissions' },
        });
        await chmod(path.join(dir, 'locked.txt'), 0o644);
      }
    } finally {
      await dispose();
    }
  });

  it('normalizes symlinked parents and files at the seam', async () => {
    const dir = await makeDir();
    await mkdir(path.join(dir, 'real'));
    await writeFile(path.join(dir, 'real/target.txt'), 'through the link\n');
    try {
      await symlink(path.join(dir, 'real'), path.join(dir, 'linked'), 'dir');
      await symlink(path.join(dir, 'real/target.txt'), path.join(dir, 'alias.txt'), 'file');
    } catch {
      return;
    }
    const { connection, dispose } = await makeRuntime();

    try {
      await expect(
        connection.api.content
          .state({ path: runtimeRoot(path.join(dir, 'linked/target.txt')) }, 'content')
          .snapshot()
      ).resolves.toMatchObject({ data: { kind: 'text', content: 'through the link\n' } });
      await expect(
        connection.api.fs.realPath({ path: runtimeRoot(path.join(dir, 'alias.txt')) })
      ).resolves.toEqual({
        success: true,
        data: { path: runtimeRoot(path.join(dir, 'real/target.txt')) },
      });
    } finally {
      await dispose();
    }
  });

  it('rejects the filesystem root itself as an absolute file key', async () => {
    const { connection, dispose } = await makeRuntime();
    const fsRoot: HostAbsolutePath =
      process.platform === 'win32'
        ? ({ root: { kind: 'drive', driveLetter: 'C' }, segments: [] } as HostAbsolutePath)
        : ({ root: { kind: 'posix' }, segments: [] } as HostAbsolutePath);

    try {
      await expect(connection.api.fs.readText({ path: fsRoot })).resolves.toMatchObject({
        success: false,
        error: { type: 'invalid-path' },
      });
    } finally {
      await dispose();
    }
  });
});

async function makeRuntime(options: FilesRuntimeOptions = {}) {
  const runtime = new FilesRuntime({
    watcher: options.watcher ?? new ManualWatcher(),
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
  const dir = await realpath(await mkdtemp(path.join(tmpdir(), 'emdash-files-absolute-')));
  roots.push(dir);
  return dir;
}

class ManualWatcher implements IWatchService {
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

  watchedRoots(): string[] {
    return [...this.entries.keys()];
  }

  optionsFor(root: string): WatchOptions | undefined {
    return this.entries.get(root)?.options;
  }

  emit(root: string, events: WatchEvent[]): void {
    this.entries.get(root)?.onEvents(events);
  }

  resync(root: string): void {
    this.entries.get(root)?.options.onResync?.();
  }

  async dispose(): Promise<void> {
    this.entries.clear();
  }
}
