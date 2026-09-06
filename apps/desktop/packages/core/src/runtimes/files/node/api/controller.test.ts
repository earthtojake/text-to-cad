import { mkdir, mkdtemp, readFile, realpath, rm, symlink, writeFile } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import path from 'node:path';
import { PassThrough } from 'node:stream';
import { ok } from '@emdash/shared';
import { waitFor } from '@emdash/shared/testing';
import { createLiveJobReplicaCache } from '@emdash/wire/live';
import {
  client,
  connect,
  memoryTransportPair,
  serve,
  streamTransport,
  type LiveUpdate,
} from '@emdash/wire/rpc';
import { afterEach, describe, expect, it } from 'vitest';
import { filesContract } from '#runtimes/files/api';
import { FilesRuntime } from '#runtimes/files/node/files-runtime';
import { relativePath, runtimeRoot } from '#runtimes/files/node/testing/paths';
import type { IWatchService, WatchEvent, WatchOptions } from '#services/fs-watch/api';
import { createFilesController } from './controller';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe('createFilesController', () => {
  it('serves filesystem, tree, content, mutation, and download behavior through Wire', async () => {
    const root = await makeRoot();
    const rootRef = runtimeRoot(root);
    await mkdir(path.join(root, 'src/foo'), { recursive: true });
    await writeFile(path.join(root, 'src/foo/bar.ts'), 'before\n');
    const watcher = new ManualWatcher();
    const runtime = new FilesRuntime({ watcher, idleTtlMs: 10_000 });
    const connection = makeClient(runtime);
    const key = { root: rootRef, sessionId: 'session-1' };
    let detachTree: (() => void) | undefined;

    try {
      await expect(connection.api.getHomeDir()).resolves.toEqual({
        path: runtimeRoot(await realpath(homedir())),
      });
      await expect(connection.api.tree.model.state(key, 'tree').snapshot()).resolves.toMatchObject({
        data: { entries: { '': { childrenLoaded: false } } },
      });
      for (const entryPath of ['', 'src', 'src/foo']) {
        const expanded = await connection.api.tree.model.mutate('expand', {
          key,
          input: { path: relativePath(entryPath) },
        });
        expect(expanded).toMatchObject({ success: true });
        if (entryPath === '' && expanded.success) {
          expect(expanded.data.cursors).toEqual([
            {
              model: filesContract.tree.model.states.tree.id,
              key,
              cursor: expect.objectContaining({ sequence: 1 }),
            },
          ]);
        }
      }

      await expect(connection.api.tree.model.state(key, 'tree').snapshot()).resolves.toMatchObject({
        data: {
          entries: {
            'src/foo/bar.ts': { kind: 'file', parentPath: 'src/foo' },
          },
        },
      });
      const treeState = connection.api.tree.model.state(key, 'tree');
      const treeUpdates: LiveUpdate[] = [];
      detachTree = await treeState.attach((update) => treeUpdates.push(update));
      await expect(
        connection.api.content
          .state({ path: runtimeRoot(path.join(root, 'src/foo/bar.ts')) }, 'content')
          .snapshot()
      ).resolves.toMatchObject({ data: { kind: 'text', content: 'before\n' } });

      await expect(
        connection.api.fs.rename({
          from: runtimeRoot(path.join(root, 'src/foo/bar.ts')),
          to: runtimeRoot(path.join(root, 'src/foo/baar.ts')),
        })
      ).resolves.toMatchObject({ success: true });
      await waitFor(async () => {
        const snapshot = await connection.api.tree.model.state(key, 'tree').snapshot();
        return (
          snapshot.data.entries['src/foo/bar.ts'] === undefined &&
          snapshot.data.entries['src/foo/baar.ts']?.kind === 'file'
        );
      });
      expect(treeUpdates).toContainEqual(
        expect.objectContaining({
          delta: expect.arrayContaining([
            expect.objectContaining({ path: ['entries', 'src/foo/bar.ts'] }),
          ]),
        })
      );
      expect(
        treeUpdates.every(
          (update) =>
            Array.isArray(update.delta) &&
            !update.delta.some((patch) => Array.isArray(patch.path) && patch.path.length === 0)
        )
      ).toBe(true);
      await expect(
        connection.api.content
          .state({ path: runtimeRoot(path.join(root, 'src/foo/bar.ts')) }, 'content')
          .snapshot()
      ).resolves.toMatchObject({ data: { kind: 'unavailable', code: 'not-found' } });

      // Content sessions watch the file's parent directory, so external edits
      // are observed there rather than through the tree root's watch.
      await writeFile(path.join(root, 'src/foo/baar.ts'), 'external\n');
      watcher.emit(path.join(root, 'src/foo'), [
        { kind: 'update', path: path.join(root, 'src/foo/baar.ts') },
      ]);
      await waitFor(async () => {
        const snapshot = await connection.api.content
          .state({ path: runtimeRoot(path.join(root, 'src/foo/baar.ts')) }, 'content')
          .snapshot();
        return snapshot.data.kind === 'text' && snapshot.data.content === 'external\n';
      });

      const contentKey = { path: runtimeRoot(path.join(root, 'src/foo/baar.ts')) };
      const beforeSave = await connection.api.content.state(contentKey, 'content').snapshot();
      expect(beforeSave.data.kind).toBe('text');
      if (beforeSave.data.kind !== 'text') throw new Error('Expected text content');
      await expect(
        connection.api.content.mutate('write', {
          key: contentKey,
          input: {
            content: 'saved\n',
            precondition: { kind: 'etag', etag: beforeSave.data.etag },
          },
        })
      ).resolves.toMatchObject({ success: true });
      await expect(
        connection.api.content.state(contentKey, 'content').snapshot()
      ).resolves.toMatchObject({
        data: { kind: 'text', content: 'saved\n', etag: expect.stringMatching(/^sha256:/u) },
      });

      await writeFile(path.join(root, 'src/foo/baar.ts'), 'newer external\n');
      watcher.emit(path.join(root, 'src/foo'), [
        { kind: 'update', path: path.join(root, 'src/foo/baar.ts') },
      ]);
      await waitFor(async () => {
        const snapshot = await connection.api.content.state(contentKey, 'content').snapshot();
        return snapshot.data.kind === 'text' && snapshot.data.content === 'newer external\n';
      });
      await expect(
        connection.api.content.mutate('write', {
          key: contentKey,
          input: {
            content: 'must not overwrite\n',
            precondition: { kind: 'etag', etag: beforeSave.data.etag },
          },
        })
      ).resolves.toMatchObject({ success: false, error: { type: 'etag-mismatch' } });

      // A live not-found content session recovers when an fs mutation makes
      // the file appear (ack-time republish, no watcher event involved).
      await mkdir(path.join(root, 'incoming/nested'), { recursive: true });
      await writeFile(path.join(root, 'incoming/nested/arrived.txt'), 'arrived');
      const arrivedKey = { path: runtimeRoot(path.join(root, 'arrived.txt')) };
      await expect(
        connection.api.content.state(arrivedKey, 'content').snapshot()
      ).resolves.toMatchObject({ data: { kind: 'unavailable', code: 'not-found' } });
      await expect(
        connection.api.fs.move({
          from: runtimeRoot(path.join(root, 'incoming/nested/arrived.txt')),
          to: runtimeRoot(path.join(root, 'arrived.txt')),
        })
      ).resolves.toMatchObject({ success: true });
      await waitFor(async () => {
        const snapshot = await connection.api.content.state(arrivedKey, 'content').snapshot();
        return snapshot.data.kind === 'text' && snapshot.data.content === 'arrived';
      });

      const download = await connection.api.fs.readBytes({
        path: runtimeRoot(path.join(root, 'src/foo/baar.ts')),
      });
      expect(download.success).toBe(true);
      if (download.success) {
        expect(download.data.meta).toMatchObject({ name: 'baar.ts', truncated: false });
        expect(Buffer.from(await download.data.bytes()).toString('utf8')).toBe('newer external\n');
      }
    } finally {
      detachTree?.();
      connection.dispose();
      await runtime.dispose();
    }
  });

  it('cannot follow an outside-parent symlink but deletes the link itself', async () => {
    const root = await makeRoot();
    const outside = await makeRoot();
    const outsideFile = path.join(outside, 'outside.txt');
    await writeFile(outsideFile, 'keep');
    try {
      await symlink(outsideFile, path.join(root, 'outside-link'), 'file');
    } catch {
      return;
    }
    const runtime = new FilesRuntime({ watcher: new ManualWatcher() });
    const connection = makeClient(runtime);

    try {
      await expect(
        connection.api.fs.readText({ path: runtimeRoot(path.join(root, 'outside-link')) })
      ).resolves.toMatchObject({ success: false, error: { type: 'invalid-path' } });
      await expect(
        connection.api.fs.delete({ path: runtimeRoot(path.join(root, 'outside-link')) })
      ).resolves.toMatchObject({ success: true });
      await expect(readFile(outsideFile, 'utf8')).resolves.toBe('keep');
    } finally {
      connection.dispose();
      await runtime.dispose();
    }
  });

  it('keeps expansion state per session and rebuilds each loaded frontier on resync', async () => {
    const root = await makeRoot();
    const rootRef = runtimeRoot(root);
    await mkdir(path.join(root, 'src/nested'), { recursive: true });
    await writeFile(path.join(root, 'src/nested/file.ts'), 'one');
    const watcher = new ManualWatcher();
    const runtime = new FilesRuntime({ watcher, idleTtlMs: 10_000 });
    const connection = makeClient(runtime);
    const first = { root: rootRef, sessionId: 'first' };
    const second = { root: rootRef, sessionId: 'second' };

    try {
      await connection.api.tree.model.state(first, 'tree').snapshot();
      await connection.api.tree.model.state(second, 'tree').snapshot();
      await expect(
        connection.api.tree.model.mutate('reveal', {
          key: first,
          input: { path: relativePath('src/nested/file.ts') },
        })
      ).resolves.toMatchObject({ success: true });

      await expect(
        connection.api.tree.model.state(first, 'tree').snapshot()
      ).resolves.toMatchObject({
        data: {
          entries: {
            src: { childrenLoaded: true },
            'src/nested': { childrenLoaded: true },
            'src/nested/file.ts': { kind: 'file' },
          },
        },
      });
      await expect(
        connection.api.tree.model.state(second, 'tree').snapshot()
      ).resolves.toMatchObject({ data: { entries: { '': { childrenLoaded: false } } } });

      await rm(path.join(root, 'src/nested/file.ts'));
      await writeFile(path.join(root, 'src/nested/new.ts'), 'two');
      watcher.resync(root);
      await waitFor(async () => {
        const snapshot = await connection.api.tree.model.state(first, 'tree').snapshot();
        return (
          snapshot.data.entries['src/nested/file.ts'] === undefined &&
          snapshot.data.entries['src/nested/new.ts']?.kind === 'file'
        );
      });
      const secondSnapshot = await connection.api.tree.model.state(second, 'tree').snapshot();
      expect(Object.keys(secondSnapshot.data.entries)).toEqual(['']);
    } finally {
      connection.dispose();
      await runtime.dispose();
    }
  });

  it('refreshes loaded directory symlinks when their target changes', async () => {
    const root = await makeRoot();
    const rootRef = runtimeRoot(root);
    await mkdir(path.join(root, 'first'));
    await mkdir(path.join(root, 'second'));
    await writeFile(path.join(root, 'first/a.txt'), 'a');
    await writeFile(path.join(root, 'second/b.txt'), 'b');
    try {
      await symlink('first', path.join(root, 'linked'), 'dir');
    } catch {
      return;
    }
    const watcher = new ManualWatcher();
    const runtime = new FilesRuntime({ watcher, idleTtlMs: 10_000 });
    const connection = makeClient(runtime);
    const key = { root: rootRef, sessionId: 'symlink-target' };

    try {
      await connection.api.tree.model.state(key, 'tree').snapshot();
      await connection.api.tree.model.mutate('expand', {
        key,
        input: { path: relativePath('') },
      });
      await connection.api.tree.model.mutate('expand', {
        key,
        input: { path: relativePath('linked') },
      });
      await expect(connection.api.tree.model.state(key, 'tree').snapshot()).resolves.toMatchObject({
        data: { entries: { 'linked/a.txt': { kind: 'file' } } },
      });

      await rm(path.join(root, 'linked'));
      await symlink('second', path.join(root, 'linked'), 'dir');
      watcher.emit(root, [{ kind: 'update', path: path.join(root, 'linked') }]);

      await waitFor(async () => {
        const entries = (await connection.api.tree.model.state(key, 'tree').snapshot()).data
          .entries;
        return entries['linked/a.txt'] === undefined && entries['linked/b.txt']?.kind === 'file';
      });
    } finally {
      connection.dispose();
      await runtime.dispose();
    }
  });

  it('runs enumeration as a cancellable Wire job with directory-relative paths', async () => {
    const root = await makeRoot();
    await mkdir(path.join(root, 'src/nested'), { recursive: true });
    await writeFile(path.join(root, 'src/a.ts'), 'a');
    await writeFile(path.join(root, 'src/nested/b.ts'), 'b');
    await writeFile(path.join(root, 'src/nested/c.txt'), 'c');
    const runtime = new FilesRuntime({ watcher: new ManualWatcher() });
    const connection = makeClient(runtime);
    const enumerateJobs = createLiveJobReplicaCache(
      filesContract.fs.enumerate,
      connection.api.fs.enumerate
    );

    try {
      const enumerationLease = await enumerateJobs.start({
        path: runtimeRoot(path.join(root, 'src')),
      });
      const enumeration = await enumerationLease.ready();
      await expect(enumeration.result).resolves.toEqual({
        paths: ['a.ts', 'nested/b.ts', 'nested/c.txt'],
      });
      await enumerationLease.release();
    } finally {
      await enumerateJobs.dispose();
      connection.dispose();
      await runtime.dispose();
    }
  });

  it('round-trips JSON-safe state and raw downloads through stream transport', async () => {
    const root = await makeRoot();
    await writeFile(path.join(root, 'stream.txt'), 'stream\r\n');
    const runtime = new FilesRuntime({ watcher: new ManualWatcher() });
    const connection = makeStreamClient(runtime);

    try {
      const metadata = await connection.api.fs.stat({
        path: runtimeRoot(path.join(root, 'stream.txt')),
      });
      expect(metadata).toMatchObject({
        success: true,
        data: { path: 'stream.txt', type: 'file' },
      });
      if (metadata.success) {
        expect(metadata.data.mtimeMs).toBeTypeOf('number');
        expect(metadata.data.ctimeMs).toBeTypeOf('number');
      }

      await expect(
        connection.api.content
          .state({ path: runtimeRoot(path.join(root, 'stream.txt')) }, 'content')
          .snapshot()
      ).resolves.toMatchObject({ data: { kind: 'text', eol: 'crlf', content: 'stream\r\n' } });

      const download = await connection.api.fs.readBytes({
        path: runtimeRoot(path.join(root, 'stream.txt')),
      });
      expect(download.success).toBe(true);
      if (download.success) {
        expect(Buffer.from(await download.data.bytes()).toString('utf8')).toBe('stream\r\n');
      }

      const uploadBytes = Buffer.from('uploaded through Wire\n');
      await expect(
        connection.api.fs.upload(
          { path: runtimeRoot(path.join(root, 'uploaded.txt')) },
          {
            name: 'uploaded.txt',
            mimeType: 'text/plain',
            size: uploadBytes.byteLength,
            source: chunks(uploadBytes),
          }
        )
      ).resolves.toEqual({ success: true, data: { bytesWritten: uploadBytes.byteLength } });
      await expect(readFile(path.join(root, 'uploaded.txt'), 'utf8')).resolves.toBe(
        'uploaded through Wire\n'
      );
    } finally {
      connection.dispose();
      await runtime.dispose();
    }
  });
});

async function* chunks(bytes: Uint8Array): AsyncIterable<Uint8Array> {
  yield bytes;
}

function makeClient(runtime: FilesRuntime) {
  const pair = memoryTransportPair();
  const controller = createFilesController(runtime);
  const stop = serve(pair.right, controller);
  return {
    api: client(filesContract, connect(pair.left)),
    dispose: () => {
      stop();
      controller.dispose?.();
    },
  };
}

function makeStreamClient(runtime: FilesRuntime) {
  const clientToServer = new PassThrough();
  const serverToClient = new PassThrough();
  const clientTransport = streamTransport(serverToClient, clientToServer);
  const serverTransport = streamTransport(clientToServer, serverToClient);
  const controller = createFilesController(runtime);
  const stop = serve(serverTransport, controller);
  return {
    api: client(filesContract, connect(clientTransport)),
    dispose: () => {
      stop();
      controller.dispose?.();
      clientTransport.close?.();
      serverTransport.close?.();
      clientToServer.destroy();
      serverToClient.destroy();
    },
  };
}

async function makeRoot(): Promise<string> {
  const root = await realpath(await mkdtemp(path.join(tmpdir(), 'emdash-files-runtime-')));
  roots.push(root);
  return root;
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
