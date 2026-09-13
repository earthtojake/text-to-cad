import { mkdtemp, realpath, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import { deferred } from '@emdash/shared/testing';
import { afterEach, describe, expect, it } from 'vitest';
import { resolveRootIdentity, type RootIdentity } from '#runtimes/files/node/allocation/identity';
import { runtimeRoot } from '#runtimes/files/node/testing/paths';
import type { IWatchService, WatchEvent, WatchOptions } from '#services/fs-watch/api';
import { RootResource, type RootChange } from './root-resource';

const cleanups: Array<() => void | Promise<void>> = [];

afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup();
});

describe('RootResource', () => {
  it('creates without waiting for watcher readiness', async () => {
    // Regression: reveal/expand and content first-reads must not block on the
    // fs-watch attach barrier (native watcher startup can be slow or fail).
    const identity = await createIdentity();
    const watcher = new PendingWatcher();

    const root = await RootResource.create({ identity, watcher });
    cleanups.push(() => root.dispose());

    expect(watcher.readyResolved).toBe(false);
    expect(root.subscribe(() => {})).toBeTypeOf('function');
  });

  it('emits a resync once the watcher becomes ready', async () => {
    const identity = await createIdentity();
    const watcher = new PendingWatcher();
    const root = await RootResource.create({ identity, watcher });
    cleanups.push(() => root.dispose());
    const batches: RootChange[][] = [];
    root.subscribe((changes) => batches.push(changes));

    watcher.ready.resolve(ok(undefined));
    await root.watchReady();

    expect(batches).toEqual([[{ kind: 'resync' }]]);
  });

  it('keeps serving after watcher startup fails and reports the error', async () => {
    const identity = await createIdentity();
    const watcher = new PendingWatcher();
    const errors: Array<{ context: string; error: unknown }> = [];
    const root = await RootResource.create({
      identity,
      watcher,
      onError: (context, error) => errors.push({ context, error }),
    });
    cleanups.push(() => root.dispose());

    watcher.ready.resolve(err(new Error('native watcher startup failed')));
    await root.watchReady();

    expect(errors).toHaveLength(1);
    expect(errors[0]?.context).toContain('files root watch');
    const batches: RootChange[][] = [];
    root.subscribe((changes) => batches.push(changes));
    root.publishKnownChanges([{ kind: 'resync' }]);
    expect(batches).toEqual([[{ kind: 'resync' }]]);
    await expect(root.runFileMutation('/tmp/x', async () => 'ran')).resolves.toBe('ran');
  });

  it('suppresses watch startup errors caused by disposal', async () => {
    const identity = await createIdentity();
    const watcher = new PendingWatcher();
    const errors: unknown[] = [];
    const root = await RootResource.create({
      identity,
      watcher,
      onError: (_context, error) => errors.push(error),
    });

    await root.dispose();
    watcher.ready.resolve(err(new Error('released before ready')));
    await root.watchReady();

    expect(errors).toEqual([]);
    expect(watcher.released).toBe(true);
  });
});

class PendingWatcher implements IWatchService {
  readonly ready = deferred<Result<void, unknown>>();
  released = false;
  readyResolved = false;

  watch(_root: string, _onEvents: (events: WatchEvent[]) => void, _options?: WatchOptions) {
    void this.ready.promise.then(
      () => {
        this.readyResolved = true;
      },
      () => {}
    );
    return {
      ready: () => this.ready.promise,
      release: async () => {
        this.released = true;
      },
    };
  }

  async dispose(): Promise<void> {}
}

async function createIdentity(): Promise<RootIdentity> {
  const rootPath = await realpath(await mkdtemp(path.join(tmpdir(), 'emdash-root-resource-')));
  cleanups.push(() => rm(rootPath, { recursive: true, force: true }));
  const resolved = await resolveRootIdentity(runtimeRoot(rootPath));
  if (!resolved.success) throw new Error(`Unable to resolve test root: ${resolved.error.type}`);
  return resolved.data;
}
