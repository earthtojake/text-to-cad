import type { Run, Scope } from '@emdash/shared/concurrency';
import { throwIfAborted, waitWithSignal } from '@emdash/shared/scheduling';
import {
  ROOT_RELATIVE_PATH,
  type HostAbsolutePath,
  type PortableRelativePath,
} from '#primitives/path/api';
import type { PathSearchError } from '#runtimes/file-search/api';
import type { IWatchService, WatchEvent, WatchHandle } from '#services/fs-watch/api';
import { toExpectedRootOrIndexError } from '../../error-mapping';
import type { FileSearchExclusions } from '../../exclusions';
import { hostAbsolutePathFromNative } from '../../native-paths';
import type { StoredFileSearchRoot } from '../../root/registered-root';
import { affectedSubtrees } from './affected-subtrees';
import { RootWatchError } from './errors';
import type {
  PathIndexBuild,
  PathIndexEntry,
  PathIndexPatch,
  PathIndexStore,
} from './path-index-store';
import type { PathScanner } from './scanner';

const WATCH_DEBOUNCE_MS = 50;
const SCAN_WRITE_BATCH_SIZE = 500;

type RunPathScan = <T>(signal: AbortSignal, operation: () => Promise<T>) => Promise<T>;

type RootIndexOptions = Readonly<{
  root: StoredFileSearchRoot;
  store: PathIndexStore;
  watcher: IWatchService;
  scanner: PathScanner;
  exclusions: FileSearchExclusions;
  scope: Scope;
  runScan: RunPathScan;
  onError?: (context: string, error: unknown) => void;
}>;

export type RootIndexFailure =
  | Readonly<{ expected: PathSearchError }>
  | Readonly<{ unexpected: unknown }>;

export type RootIndexStatus =
  | Readonly<{ kind: 'building' }>
  | Readonly<{ kind: 'ready' }>
  | Readonly<{ kind: 'failed'; failure: RootIndexFailure }>;

/** Keeps one registered root's published path generation current. */
export class RootIndex {
  private readonly scope: Scope;
  private readonly watch: WatchHandle;
  private readonly root: HostAbsolutePath;
  private publicationState:
    | { kind: 'published' }
    | { kind: 'building'; patches: PathIndexPatch[] } = {
    kind: 'published',
  };
  private eventQueue: Promise<void> = Promise.resolve();
  private reconcileRun: Run<void> | undefined;
  private trailingReconcileRequested = false;
  private currentStatus: RootIndexStatus = { kind: 'building' };

  constructor(private readonly options: RootIndexOptions) {
    this.root = hostAbsolutePathFromNative(options.root.rootPath);
    this.scope = options.scope.child(`file-search-root-${options.root.id}`);
    try {
      this.watch = options.watcher.watch(
        options.root.rootPath,
        (events) => this.enqueueEvents(events),
        {
          debounceMs: WATCH_DEBOUNCE_MS,
          ignore: [...options.exclusions.watchIgnoreGlobs()],
          onResync: () => this.requestReconcile(),
        }
      );
    } catch (error) {
      throw new RootWatchError('File-search watcher could not be created for the root', error);
    }
    this.scope.add(() => this.watch.release());
  }

  get status(): RootIndexStatus {
    return this.currentStatus;
  }

  /** Coalesces concurrent requests and settles when the current reconciliation attempt settles. */
  reconcile(): Promise<void> {
    if (this.scope.state !== 'open') {
      return Promise.reject(new Error('Root index is disposed'));
    }
    if (this.reconcileRun) return this.reconcileRun.value();

    if (this.currentStatus.kind !== 'failed') this.currentStatus = { kind: 'building' };
    const run = this.scope.run('reconcile', (signal) => this.reconcileLoop(signal));
    this.reconcileRun = run;
    void run.exit.then(() => {
      if (this.reconcileRun === run) this.reconcileRun = undefined;
      if (this.trailingReconcileRequested && this.scope.state === 'open') {
        this.trailingReconcileRequested = false;
        this.requestReconcile();
      }
    });
    return run.value();
  }

  private async reconcileLoop(signal: AbortSignal): Promise<void> {
    do {
      this.trailingReconcileRequested = false;
      await this.reconcileOnce(signal);
    } while (this.trailingReconcileRequested && this.scope.state === 'open');
  }

  private async reconcileOnce(signal: AbortSignal): Promise<void> {
    let build: PathIndexBuild | undefined;
    try {
      const attached = await waitWithSignal(this.watch.ready(), signal, 'Root index cancelled');
      if (!attached.success) {
        throw new RootWatchError(
          'File-search watcher could not attach to the root',
          attached.error
        );
      }
      throwIfAborted(signal, 'Root index cancelled');
      const activeBuild = this.options.store.beginBuild(this.options.root.id);
      build = activeBuild;
      this.publicationState = { kind: 'building', patches: [] };

      await this.options.runScan(signal, () => this.populateBuild(activeBuild, signal));

      // Events already queued run before this barrier. Later events run after the synchronous
      // publish below and therefore patch the newly-published generation.
      const barrier = this.eventQueue.then(() => undefined);
      this.eventQueue = barrier;
      await waitWithSignal(barrier, signal, 'Root index cancelled');
      throwIfAborted(signal, 'Root index cancelled');

      const finalPatches =
        this.publicationState.kind === 'building' ? this.publicationState.patches : [];
      activeBuild.publish(finalPatches);
      this.publicationState = { kind: 'published' };
      if (!this.trailingReconcileRequested) this.currentStatus = { kind: 'ready' };
    } catch (error) {
      if (build) {
        try {
          build.discard();
        } catch (discardError) {
          this.report('file-search path-index discard failed', discardError);
        }
      }
      this.publicationState = { kind: 'published' };
      this.currentStatus = { kind: 'failed', failure: this.classifyFailure(error) };
      throw error;
    }
  }

  private async populateBuild(build: PathIndexBuild, signal: AbortSignal): Promise<void> {
    let batch: PathIndexEntry[] = [];
    for await (const entry of this.options.scanner.scan(
      this.options.root.rootPath,
      ROOT_RELATIVE_PATH,
      { signal, exclusions: this.options.exclusions }
    )) {
      batch.push(entry);
      if (batch.length < SCAN_WRITE_BATCH_SIZE) continue;
      build.append(batch);
      batch = [];
    }
    if (batch.length > 0) build.append(batch);
  }

  private enqueueEvents(events: WatchEvent[]): void {
    if (this.scope.state !== 'open' || events.length === 0) return;
    if (events.every((event) => event.kind === 'update')) {
      if (this.currentStatus.kind === 'ready') return;
      if (this.currentStatus.kind === 'failed') {
        this.requestReconcile();
        return;
      }
    }

    const previous = this.eventQueue;
    const run = this.scope.run('watch-patch', async (signal) => {
      await waitWithSignal(previous, signal, 'Root index cancelled');
      const paths = affectedSubtrees(events, this.options.root.rootPath, this.options.exclusions);
      if (paths.some((entry) => entry === ROOT_RELATIVE_PATH)) {
        this.requestReconcile();
        return;
      }

      const patches: PathIndexPatch[] = [];
      for (const relativePath of paths) {
        patches.push(await this.patchForPath(relativePath, signal));
      }
      if (patches.length === 0) return;

      if (this.publicationState.kind === 'building') {
        this.publicationState.patches.push(...patches);
      } else this.options.store.applyPublishedPatches(this.options.root.id, patches);
    });
    this.eventQueue = run.value().catch((error: unknown) => {
      if (this.scope.signal.aborted) return;
      this.currentStatus = { kind: 'failed', failure: this.classifyFailure(error) };
      this.report('file-search watcher patch failed', error);
      this.requestReconcile();
    });
  }

  private async patchForPath(
    relativePath: PortableRelativePath,
    signal: AbortSignal
  ): Promise<PathIndexPatch> {
    const entries: PathIndexEntry[] = [];
    await this.options.runScan(signal, async () => {
      for await (const entry of this.options.scanner.scan(
        this.options.root.rootPath,
        relativePath,
        { signal, exclusions: this.options.exclusions }
      )) {
        entries.push(entry);
      }
    });

    if (entries.length === 1 && entries[0].path === relativePath && entries[0].kind === 'file') {
      return { kind: 'upsert', entry: entries[0] };
    }
    if (entries.length === 0) return { kind: 'delete-subtree', path: relativePath };
    return { kind: 'replace-subtree', path: relativePath, entries };
  }

  private requestReconcile(): void {
    if (this.scope.state !== 'open') return;
    if (this.reconcileRun) {
      this.trailingReconcileRequested = true;
      return;
    }
    void this.reconcile().catch((error: unknown) => {
      if (!this.scope.signal.aborted) {
        this.report('file-search reconciliation failed', error);
      }
    });
  }

  private report(context: string, error: unknown): void {
    this.options.onError?.(context, error);
  }

  private classifyFailure(error: unknown): RootIndexFailure {
    const expected = toExpectedRootOrIndexError(
      this.root,
      error,
      'The file-search index could not be built',
      'path-index'
    );
    return expected ? { expected } : { unexpected: error };
  }
}
