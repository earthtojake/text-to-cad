import { mkdtemp, realpath, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import type Database from 'better-sqlite3';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { StoreHandle } from '#primitives/sqlite-store/api';
import { RootWatchError } from '../path/index/errors';
import type { RootIndex } from '../path/index/root-index';
import { SqliteFileSearchStore } from '../storage/sqlite-file-search-store';
import { fileSearchStore, type FileSearchDb } from '../storage/store';
import { hostPath as absolute } from '../testing/paths';
import type { RegisteredRoot, StoredFileSearchRoot } from './registered-root';
import { NodeFileSearchRootResolver } from './root-identity';
import { FileSearchRootRegistry } from './root-registry';

const cleanups: Array<() => void | Promise<void>> = [];
const storeHandles = new WeakMap<
  SqliteFileSearchStore,
  StoreHandle<FileSearchDb, Database.Database>
>();

afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup();
});

describe('FileSearchRootRegistry', () => {
  it('constructs a registered root from the persisted record and lifecycle scope', async () => {
    const rootPath = await createRoot();
    const createRegistered = vi.fn(fakeRoot);
    const { registry } = createRegistry({ createRoot: createRegistered });
    const root = absolute(rootPath);

    await expect(registry.registerRoot({ root })).resolves.toEqual({
      success: true,
      data: undefined,
    });
    expect(createRegistered).toHaveBeenCalledOnce();
    expect(createRegistered.mock.calls[0][0]).toMatchObject({ rootPath });
    expect(createRegistered.mock.calls[0][1].state).toBe('open');
    expect(registry.resolveRegisteredRoot(root)).toMatchObject({ success: true });
  });

  it('re-registers and rebuilds the index when exclusions differ from the ready root', async () => {
    const rootPath = await createRoot();
    const createRegistered = vi.fn(fakeRoot);
    const { registry } = createRegistry({ createRoot: createRegistered });
    const root = absolute(rootPath);

    // First registration — empty default patterns.
    await registry.registerRoot({ root });
    expect(createRegistered).toHaveBeenCalledTimes(1);

    // Second registration with different exclusions — fingerprint mismatch triggers rebuild.
    await registry.registerRoot({ root, exclusions: ['node_modules'] });
    expect(createRegistered).toHaveBeenCalledTimes(2);

    // Catalog row must be preserved (not re-created).
    const resolved = registry.resolveRegisteredRoot(root);
    expect(resolved).toMatchObject({ success: true });
  });

  it('does not rebuild the index when the same exclusion set is re-registered (order-insensitive)', async () => {
    const rootPath = await createRoot();
    const createRegistered = vi.fn(fakeRoot);
    const { registry } = createRegistry({ createRoot: createRegistered });
    const root = absolute(rootPath);

    await registry.registerRoot({ root, exclusions: ['dist', 'build'] });
    await registry.registerRoot({ root, exclusions: ['build', 'dist'] });

    // Same canonical set — no stop+start should occur.
    expect(createRegistered).toHaveBeenCalledTimes(1);
  });

  it('keeps durable registrations when registry shutdown stops maintenance', async () => {
    const rootPath = await createRoot();
    const { registry, store } = createRegistry();
    await registry.registerRoot({ root: absolute(rootPath) });

    await registry.dispose();

    expect(store.listRoots()).toHaveLength(1);
  });

  it('explicitly removes a persisted root whose restoration failed to start', async () => {
    const rootPath = await createRoot();
    const root = absolute(rootPath);
    const resolver = new NodeFileSearchRootResolver();
    const resolved = await resolver.resolve(root);
    if (!resolved.success) throw new Error('Expected root to resolve');
    const store = createStore();
    store.upsertRoot(resolved.data);
    await rm(rootPath, { recursive: true, force: true });
    const { registry } = createRegistry({ store });

    await vi.waitFor(() =>
      expect(registry.resolveRegisteredRoot(root)).toMatchObject({
        success: false,
        error: { type: 'root-unavailable' },
      })
    );
    await expect(registry.unregisterRoot({ root })).resolves.toEqual({
      success: true,
      data: undefined,
    });
    expect(store.listRoots()).toEqual([]);
    expect(registry.resolveRegisteredRoot(root)).toMatchObject({
      success: false,
      error: { type: 'root-not-registered' },
    });
  });

  it('rolls back a new durable row when registered-root construction fails', async () => {
    const rootPath = await createRoot();
    const failure = Object.assign(new Error('root disappeared'), { code: 'ENOENT' });
    const { registry, store } = createRegistry({
      createRoot: (_record, _scope, _exclusions, _fingerprint) => {
        throw new RootWatchError('File-search watcher could not be created for the root', failure);
      },
    });

    await expect(registry.registerRoot({ root: absolute(rootPath) })).resolves.toMatchObject({
      success: false,
      error: { type: 'root-unavailable', reason: 'not-found' },
    });
    expect(store.listRoots()).toEqual([]);
  });

  it('throws when registration and its persistence rollback both fail', async () => {
    const rootPath = await createRoot();
    const attachmentFailure = Object.assign(new Error('root disappeared'), { code: 'ENOENT' });
    const rollbackFailure = Object.assign(new Error('database busy'), { code: 'SQLITE_BUSY' });
    const store = createStore();
    vi.spyOn(store, 'deleteRoot').mockImplementation(() => {
      throw rollbackFailure;
    });
    const { registry } = createRegistry({
      store,
      createRoot: (_record, _scope, _exclusions, _fingerprint) => {
        throw new RootWatchError(
          'File-search watcher could not be created for the root',
          attachmentFailure
        );
      },
    });

    const registration = registry.registerRoot({ root: absolute(rootPath) });
    await expect(registration).rejects.toBeInstanceOf(AggregateError);
    await expect(registration).rejects.toMatchObject({
      errors: [{ cause: attachmentFailure }, rollbackFailure],
    });
    expect(store.listRoots()).toHaveLength(1);
  });
});

function createRegistry(
  options: {
    store?: SqliteFileSearchStore;
    createRoot?: (
      record: StoredFileSearchRoot,
      scope: Scope,
      exclusions: unknown,
      fingerprint: string
    ) => RegisteredRoot;
  } = {}
): { registry: FileSearchRootRegistry; store: SqliteFileSearchStore; scope: Scope } {
  const store = options.store ?? createStore();
  const scope = createScope({ label: 'root-registry-test' });
  const registry = new FileSearchRootRegistry({
    catalog: store,
    resolver: new NodeFileSearchRootResolver(),
    createRoot: options.createRoot ?? fakeRoot,
    compileExclusions: () => ({
      excludes: () => false,
      ripgrepGlobs: () => [],
      watchIgnoreGlobs: () => [],
    }),
    defaultExclusionPatterns: [],
    scope,
  });
  cleanups.push(async () => {
    await registry.dispose();
    await scope.dispose();
    storeHandles.get(store)?.close();
  });
  return { registry, store, scope };
}

function createStore(): SqliteFileSearchStore {
  const handle = fileSearchStore.open(':memory:');
  const store = new SqliteFileSearchStore(handle);
  storeHandles.set(store, handle);
  return store;
}

function fakeRoot(
  record: StoredFileSearchRoot,
  scope: Scope,
  _exclusions: unknown,
  exclusionsFingerprint: string
): RegisteredRoot {
  return { record, scope, index: {} as RootIndex, exclusionsFingerprint };
}

async function createRoot(): Promise<string> {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'emdash-root-registry-'));
  cleanups.push(() => rm(directory, { recursive: true, force: true }));
  return realpath(directory);
}
