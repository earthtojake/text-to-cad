import { mkdtemp, mkdir, realpath, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import { deferred } from '@emdash/shared/testing';
import { afterEach, describe, expect, it } from 'vitest';
import type { PortableRelativePath } from '#primitives/path/api';
import type { PathSearchHit } from '#runtimes/file-search/api';
import type { IWatchService, WatchEvent, WatchHandle, WatchOptions } from '#services/fs-watch/api';
import { DefaultFileSearchExclusions } from '../../exclusions';
import { SqliteFileSearchStore } from '../../storage/sqlite-file-search-store';
import { fileSearchStore } from '../../storage/store';
import type {
  PathIndexBuild,
  PathIndexEntry,
  PathIndexPatch,
  PathIndexStore,
} from './path-index-store';
import { RootIndex } from './root-index';
import { NodePathScanner, type PathScanner, type PathScanOptions } from './scanner';

const cleanups: Array<() => void | Promise<void>> = [];

afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup();
});

describe('RootIndex', () => {
  it('publishes a full scan and translates file and directory watch signals into patches', async () => {
    const rootPath = await createRoot();
    await mkdir(path.join(rootPath, 'src'));
    await writeFile(path.join(rootPath, 'src', 'old.ts'), 'old');
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath }).root;
    const watcher = new FakeWatchService();
    const scope = createScope({ label: 'root-index-test' });
    const index = new RootIndex({
      root,
      store,
      watcher,
      scanner: new NodePathScanner(),
      exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
      scope,
      runScan: async (_signal, operation) => operation(),
    });
    cleanups.push(() => scope.dispose());

    await index.reconcile();
    expect(hits(store)).toEqual([
      { path: 'src', kind: 'directory' },
      { path: 'src/old.ts', kind: 'file' },
    ]);

    await rm(path.join(rootPath, 'src'), { recursive: true });
    watcher.emit([{ kind: 'delete', path: path.join(rootPath, 'src') }]);
    await eventually(() => expect(hits(store)).toEqual([]));

    await mkdir(path.join(rootPath, 'lib'));
    await writeFile(path.join(rootPath, 'lib', 'new.ts'), 'new');
    watcher.emit([{ kind: 'create', path: path.join(rootPath, 'lib') }]);
    await eventually(() =>
      expect(hits(store)).toEqual([
        { path: 'lib', kind: 'directory' },
        { path: 'lib/new.ts', kind: 'file' },
      ])
    );
  });

  it('applies the root exclusion policy during full scans', async () => {
    const rootPath = await createRoot();
    await mkdir(path.join(rootPath, 'src'));
    await mkdir(path.join(rootPath, 'generated'));
    await writeFile(path.join(rootPath, 'src', 'app.ts'), 'app');
    await writeFile(path.join(rootPath, 'generated', 'client.ts'), 'generated');
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath }).root;
    const watcher = new FakeWatchService();
    const scope = createScope({ label: 'root-index-exclusions-test' });
    const index = new RootIndex({
      root,
      store,
      watcher,
      scanner: new NodePathScanner(),
      exclusions: new DefaultFileSearchExclusions({
        caseSensitive: true,
        patterns: ['generated'],
      }),
      scope,
      runScan: async (_signal, operation) => operation(),
    });
    cleanups.push(() => scope.dispose());

    await index.reconcile();

    expect(hits(store)).toEqual([
      { path: 'src', kind: 'directory' },
      { path: 'src/app.ts', kind: 'file' },
    ]);
  });

  it('does not scan or write update-only batches once the index is healthy', async () => {
    const rootPath = await createRoot();
    await writeFile(path.join(rootPath, 'changed.ts'), 'before');
    const delegate = createStore();
    const root = delegate.upsertRoot({ rootKey: 'root-key', rootPath }).root;
    const store = new RecordingPatchStore(delegate);
    const watcher = new FakeWatchService();
    const scanner = new RecordingScanner();
    const scope = createScope({ label: 'root-index-update-only-test' });
    const index = new RootIndex({
      root,
      store,
      watcher,
      scanner,
      exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
      scope,
      runScan: async (_signal, operation) => operation(),
    });
    cleanups.push(() => scope.dispose());
    await index.reconcile();

    await writeFile(path.join(rootPath, 'changed.ts'), 'after');
    await writeFile(path.join(rootPath, 'created.ts'), 'new');
    watcher.emit([{ kind: 'update', path: path.join(rootPath, 'changed.ts') }]);
    watcher.emit([{ kind: 'create', path: path.join(rootPath, 'created.ts') }]);
    await eventually(() =>
      expect(hits(delegate)).toEqual([
        { path: 'changed.ts', kind: 'file' },
        { path: 'created.ts', kind: 'file' },
      ])
    );

    expect(scanner.scans).toEqual(['', 'created.ts']);
    expect(store.appliedPatches).toEqual([
      [{ kind: 'upsert', entry: { path: 'created.ts', kind: 'file' } }],
    ]);
  });

  it('uses an update-only batch to recover a failed index without patching it first', async () => {
    const rootPath = await createRoot();
    await writeFile(path.join(rootPath, 'changed.ts'), 'contents');
    const delegate = createStore();
    const root = delegate.upsertRoot({ rootKey: 'root-key', rootPath }).root;
    const store = new RecordingPatchStore(delegate);
    const watcher = new FakeWatchService();
    const failure = Object.assign(new Error('scan unavailable'), { code: 'EIO' });
    const scanner = new ControllableFullScanner(failure);
    const scope = createScope({ label: 'root-index-update-recovery-test' });
    const index = new RootIndex({
      root,
      store,
      watcher,
      scanner,
      exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
      scope,
      runScan: async (_signal, operation) => operation(),
    });
    cleanups.push(() => scope.dispose());
    await index.reconcile();

    scanner.failNextFullScan();
    await expect(index.reconcile()).rejects.toBe(failure);
    watcher.emit([{ kind: 'update', path: path.join(rootPath, 'changed.ts') }]);
    await eventually(() => expect(index.status).toEqual({ kind: 'ready' }));

    expect(scanner.scans).toEqual(['', '', '']);
    expect(store.appliedPatches).toEqual([]);
  });

  it('fully reconciles after the watcher reports a possible event gap', async () => {
    const rootPath = await createRoot();
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath }).root;
    const watcher = new FakeWatchService();
    const scope = createScope({ label: 'root-index-resync-test' });
    const index = new RootIndex({
      root,
      store,
      watcher,
      scanner: new NodePathScanner(),
      exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
      scope,
      runScan: async (_signal, operation) => operation(),
    });
    cleanups.push(() => scope.dispose());
    await index.reconcile();

    await writeFile(path.join(rootPath, 'unreported.ts'), 'new');
    watcher.resync();
    await eventually(() => expect(hits(store)).toEqual([{ path: 'unreported.ts', kind: 'file' }]));
  });

  it('applies watcher patches observed while an unpublished generation is still scanning', async () => {
    const rootPath = await createRoot();
    await writeFile(path.join(rootPath, 'before.ts'), 'before');
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath }).root;
    const watcher = new FakeWatchService();
    const scanner = new SnapshotPausingScanner();
    const scope = createScope({ label: 'root-index-buffer-test' });
    const index = new RootIndex({
      root,
      store,
      watcher,
      scanner,
      exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
      scope,
      runScan: async (_signal, operation) => operation(),
    });
    cleanups.push(() => scope.dispose());

    const reconcile = index.reconcile();
    await scanner.fullScanStarted.promise;
    await writeFile(path.join(rootPath, 'during.ts'), 'during');
    watcher.emit([{ kind: 'create', path: path.join(rootPath, 'during.ts') }]);
    await scanner.subtreeScanCompleted.promise;
    scanner.resumeFullScan.resolve();
    await reconcile;

    expect(hits(store)).toEqual([
      { path: 'before.ts', kind: 'file' },
      { path: 'during.ts', kind: 'file' },
    ]);
  });

  it('coalesces concurrent reconciliation callers onto one scan', async () => {
    const rootPath = await createRoot();
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath }).root;
    const scanner = new BlockingFullScanner();
    const scope = createScope({ label: 'root-index-coalescing-test' });
    const index = new RootIndex({
      root,
      store,
      watcher: new FakeWatchService(),
      scanner,
      exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
      scope,
      runScan: async (_signal, operation) => operation(),
    });
    cleanups.push(() => scope.dispose());

    const first = index.reconcile();
    await scanner.started.promise;
    const second = index.reconcile();
    expect(scanner.fullScans).toBe(1);

    scanner.resume.resolve();
    await Promise.all([first, second]);
    expect(index.status).toEqual({ kind: 'ready' });
  });

  it('runs one trailing reconciliation when resync is requested during a scan', async () => {
    const rootPath = await createRoot();
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath }).root;
    const watcher = new FakeWatchService();
    const scanner = new FirstScanPausingScanner();
    const scope = createScope({ label: 'root-index-trailing-reconcile-test' });
    const index = new RootIndex({
      root,
      store,
      watcher,
      scanner,
      exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
      scope,
      runScan: async (_signal, operation) => operation(),
    });
    cleanups.push(() => scope.dispose());

    const reconcile = index.reconcile();
    await scanner.firstStarted.promise;
    watcher.resync();
    scanner.resumeFirst.resolve();
    await reconcile;

    expect(scanner.fullScans).toBe(2);
    expect(index.status).toEqual({ kind: 'ready' });
  });

  it('discards a failed build and can publish a later recovery scan', async () => {
    const rootPath = await createRoot();
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath }).root;
    const failure = Object.assign(new Error('scan unavailable'), { code: 'EIO' });
    const scanner = new FailOnceScanner(failure);
    const scope = createScope({ label: 'root-index-recovery-test' });
    const index = new RootIndex({
      root,
      store,
      watcher: new FakeWatchService(),
      scanner,
      exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
      scope,
      runScan: async (_signal, operation) => operation(),
    });
    cleanups.push(() => scope.dispose());

    await expect(index.reconcile()).rejects.toBe(failure);
    expect(index.status).toMatchObject({
      kind: 'failed',
      failure: { expected: { type: 'io' } },
    });

    await expect(index.reconcile()).resolves.toBeUndefined();
    expect(scanner.fullScans).toBe(2);
    expect(index.status).toEqual({ kind: 'ready' });
  });

  it('fails reconciliation when watcher readiness returns a failure Result', async () => {
    const rootPath = await createRoot();
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath }).root;
    const failure = Object.assign(new Error('watch root disappeared'), { code: 'ENOENT' });
    const scanner = new RecordingScanner();
    const scope = createScope({ label: 'root-index-watch-failure-test' });
    const index = new RootIndex({
      root,
      store,
      watcher: new FakeWatchService(err(failure)),
      scanner,
      exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
      scope,
      runScan: async (_signal, operation) => operation(),
    });
    cleanups.push(() => scope.dispose());

    await expect(index.reconcile()).rejects.toMatchObject({
      name: 'RootWatchError',
      cause: failure,
    });
    expect(scanner.scans).toEqual([]);
    expect(index.status).toMatchObject({
      kind: 'failed',
      failure: { expected: { type: 'root-unavailable', reason: 'not-found' } },
    });
  });

  it('cancels active work and ignores later watcher events after disposal', async () => {
    const rootPath = await createRoot();
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath }).root;
    const watcher = new FakeWatchService();
    const scanner = new DisposalBlockingScanner();
    const scope = createScope({ label: 'root-index-disposal-test' });
    const index = new RootIndex({
      root,
      store,
      watcher,
      scanner,
      exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
      scope,
      runScan: async (_signal, operation) => operation(),
    });

    const reconcile = index.reconcile();
    void reconcile.catch(() => {});
    await scanner.started.promise;
    await scope.dispose(new Error('test disposal'));

    await expect(reconcile).rejects.toThrow('test disposal');
    await expect(index.reconcile()).rejects.toThrow('disposed');
    watcher.emit([{ kind: 'update', path: path.join(rootPath, 'after.ts') }]);
    expect(watcher.releaseCount).toBe(1);
  });

  it('marks the index degraded before attempting watcher-patch recovery', async () => {
    const rootPath = await createRoot();
    const delegate = createStore();
    const root = delegate.upsertRoot({ rootKey: 'root-key', rootPath }).root;
    const failure = Object.assign(new Error('patch storage unavailable'), { code: 'SQLITE_BUSY' });
    const store = new PatchFailingStore(delegate, failure);
    const watcher = new FakeWatchService();
    const scanner = new RecoveryPausingScanner();
    const scope = createScope({ label: 'root-index-degraded-test' });
    const index = new RootIndex({
      root,
      store,
      watcher,
      scanner,
      exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
      scope,
      runScan: async (_signal, operation) => operation(),
    });
    cleanups.push(() => scope.dispose());
    await index.reconcile();

    await writeFile(path.join(rootPath, 'new.ts'), 'new');
    watcher.emit([{ kind: 'create', path: path.join(rootPath, 'new.ts') }]);
    await scanner.recoveryStarted.promise;

    expect(index.status).toEqual({
      kind: 'failed',
      failure: { expected: expect.objectContaining({ type: 'io', message: failure.message }) },
    });
  });
});

class SnapshotPausingScanner implements PathScanner {
  readonly fullScanStarted = deferred<void>();
  readonly subtreeScanCompleted = deferred<void>();
  readonly resumeFullScan = deferred<void>();
  private readonly delegate = new NodePathScanner();

  async *scan(
    rootPath: string,
    relativeRoot: PortableRelativePath,
    options: PathScanOptions
  ): AsyncIterable<PathIndexEntry> {
    if (relativeRoot !== '') {
      yield* this.delegate.scan(rootPath, relativeRoot, options);
      this.subtreeScanCompleted.resolve();
      return;
    }

    const snapshot: PathIndexEntry[] = [];
    for await (const entry of this.delegate.scan(rootPath, relativeRoot, options)) {
      snapshot.push(entry);
    }
    this.fullScanStarted.resolve();
    await this.resumeFullScan.promise;
    for (const entry of snapshot) yield entry;
  }
}

class BlockingFullScanner implements PathScanner {
  readonly started = deferred<void>();
  readonly resume = deferred<void>();
  fullScans = 0;

  async *scan(): AsyncIterable<PathIndexEntry> {
    this.fullScans += 1;
    this.started.resolve();
    await this.resume.promise;
    yield* [];
  }
}

class FirstScanPausingScanner implements PathScanner {
  readonly firstStarted = deferred<void>();
  readonly resumeFirst = deferred<void>();
  fullScans = 0;

  async *scan(): AsyncIterable<PathIndexEntry> {
    this.fullScans += 1;
    if (this.fullScans === 1) {
      this.firstStarted.resolve();
      await this.resumeFirst.promise;
    }
    yield* [];
  }
}

class FailOnceScanner implements PathScanner {
  fullScans = 0;

  constructor(private readonly failure: unknown) {}

  async *scan(): AsyncIterable<PathIndexEntry> {
    this.fullScans += 1;
    if (this.fullScans === 1) throw this.failure;
    yield* [];
  }
}

class DisposalBlockingScanner implements PathScanner {
  readonly started = deferred<void>();

  async *scan(
    _rootPath: string,
    _relativeRoot: PortableRelativePath,
    options: PathScanOptions
  ): AsyncIterable<PathIndexEntry> {
    this.started.resolve();
    await new Promise<void>((_resolve, reject) => {
      const cancel = (): void => reject(options.signal.reason);
      if (options.signal.aborted) cancel();
      else options.signal.addEventListener('abort', cancel, { once: true });
    });
    yield* [];
  }
}

class RecoveryPausingScanner implements PathScanner {
  readonly recoveryStarted = deferred<void>();
  private readonly delegate = new NodePathScanner();
  private fullScans = 0;

  async *scan(
    rootPath: string,
    relativeRoot: PortableRelativePath,
    options: PathScanOptions
  ): AsyncIterable<PathIndexEntry> {
    if (relativeRoot === '') {
      this.fullScans += 1;
      if (this.fullScans > 1) {
        this.recoveryStarted.resolve();
        await new Promise<void>((resolve) => {
          if (options.signal.aborted) resolve();
          else options.signal.addEventListener('abort', () => resolve(), { once: true });
        });
        return;
      }
    }
    yield* this.delegate.scan(rootPath, relativeRoot, options);
  }
}

class RecordingScanner implements PathScanner {
  readonly scans: PortableRelativePath[] = [];
  private readonly delegate = new NodePathScanner();

  async *scan(
    rootPath: string,
    relativeRoot: PortableRelativePath,
    options: PathScanOptions
  ): AsyncIterable<PathIndexEntry> {
    this.scans.push(relativeRoot);
    yield* this.delegate.scan(rootPath, relativeRoot, options);
  }
}

class ControllableFullScanner extends RecordingScanner {
  private failNext = false;

  constructor(private readonly failure: unknown) {
    super();
  }

  failNextFullScan(): void {
    this.failNext = true;
  }

  override async *scan(
    rootPath: string,
    relativeRoot: PortableRelativePath,
    options: PathScanOptions
  ): AsyncIterable<PathIndexEntry> {
    if (relativeRoot === '' && this.failNext) {
      this.failNext = false;
      this.scans.push(relativeRoot);
      throw this.failure;
    }
    yield* super.scan(rootPath, relativeRoot, options);
  }
}

class RecordingPatchStore implements PathIndexStore {
  readonly appliedPatches: PathIndexPatch[][] = [];

  constructor(private readonly delegate: PathIndexStore) {}

  beginBuild(rootId: number): PathIndexBuild {
    return this.delegate.beginBuild(rootId);
  }

  applyPublishedPatches(rootId: number, patches: readonly PathIndexPatch[]): void {
    this.appliedPatches.push([...patches]);
    this.delegate.applyPublishedPatches(rootId, patches);
  }

  searchPaths(...args: Parameters<PathIndexStore['searchPaths']>) {
    return this.delegate.searchPaths(...args);
  }
}

class PatchFailingStore implements PathIndexStore {
  constructor(
    private readonly delegate: PathIndexStore,
    private readonly failure: unknown
  ) {}

  beginBuild(rootId: number): PathIndexBuild {
    return this.delegate.beginBuild(rootId);
  }

  applyPublishedPatches(_rootId: number, _patches: readonly PathIndexPatch[]): void {
    throw this.failure;
  }

  searchPaths(...args: Parameters<PathIndexStore['searchPaths']>) {
    return this.delegate.searchPaths(...args);
  }
}

class FakeWatchService implements IWatchService {
  private onEvents: ((events: WatchEvent[]) => void) | undefined;
  private onResync: (() => void) | undefined;
  releaseCount = 0;

  constructor(private readonly readyResult: Result<void, unknown> = ok(undefined)) {}

  watch(
    _root: string,
    onEvents: (events: WatchEvent[]) => void,
    options: WatchOptions = {}
  ): WatchHandle {
    this.onEvents = onEvents;
    this.onResync = options.onResync;
    return {
      ready: async () => this.readyResult,
      release: async () => {
        this.releaseCount += 1;
      },
    };
  }

  emit(events: WatchEvent[]): void {
    this.onEvents?.(events);
  }

  resync(): void {
    this.onResync?.();
  }

  async dispose(): Promise<void> {}
}

function createStore(): SqliteFileSearchStore {
  const handle = fileSearchStore.open(':memory:');
  const store = new SqliteFileSearchStore(handle);
  cleanups.push(() => handle.close());
  return store;
}

async function createRoot(): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), 'emdash-root-index-'));
  cleanups.push(() => rm(root, { recursive: true, force: true }));
  return realpath(root);
}

function hits(store: SqliteFileSearchStore): PathSearchHit[] {
  const result = store.searchPaths('root-key', '', ['file', 'directory'], 20);
  return result.kind === 'ready' ? result.hits : [];
}

async function eventually(assertion: () => void): Promise<void> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      assertion();
      return;
    } catch (error) {
      lastError = error;
      await new Promise((resolve) => setTimeout(resolve, 2));
    }
  }
  throw lastError;
}
