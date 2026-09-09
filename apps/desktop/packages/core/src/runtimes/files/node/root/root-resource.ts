import type { Unsubscribe } from '@emdash/shared';
import { KeyedMutex } from '@emdash/shared/concurrency';
import type { PortableRelativePath } from '#primitives/path/api';
import type { RootIdentity } from '#runtimes/files/node/allocation/identity';
import { RootPathPolicy, normalizeRelativePath } from '#runtimes/files/node/fs/path-policy';
import type { IWatchService, WatchHandle } from '#services/fs-watch/api';

const WATCH_DEBOUNCE_MS = 50;

export type RootChange =
  | { kind: 'create' | 'update' | 'delete'; path: PortableRelativePath }
  | { kind: 'resync' };

/**
 * A known change addressed by its native absolute path — the shape a
 * stateless fs mutation republishes into live tree sessions, whose roots
 * differ from the mutation's own operational root.
 */
export type AbsoluteChange = {
  kind: 'create' | 'update' | 'delete';
  absolutePath: string;
};

export type RootResourceOptions = {
  identity: RootIdentity;
  watcher: IWatchService;
  watchIgnoreGlobs?: readonly string[];
  onError?: (context: string, error: unknown) => void;
};

export class RootResource {
  readonly identity: RootIdentity;
  readonly paths: RootPathPolicy;

  private readonly listeners = new Set<(changes: RootChange[]) => void>();
  private readonly mutationMutex = new KeyedMutex();
  private readonly watch: WatchHandle;
  private readonly watchReadyPromise: Promise<void>;
  private disposed = false;

  static async create(options: RootResourceOptions): Promise<RootResource> {
    // Reads never wait on watcher readiness: tree and content consumers read
    // from disk and need the watch only for change notifications. Watch attach
    // (which awaits native watcher startup) proceeds concurrently, and the
    // post-ready resync covers changes missed during that startup window.
    return new RootResource(options);
  }

  private constructor(options: RootResourceOptions) {
    this.identity = options.identity;
    this.paths = new RootPathPolicy(options.identity.rootPath);
    this.watch = options.watcher.watch(
      options.identity.rootPath,
      (events) => {
        const changes = events.flatMap((event): RootChange[] => {
          const relative = this.paths.toRelative(event.path);
          return relative === null ? [] : [{ kind: event.kind, path: relative }];
        });
        this.emit(changes);
      },
      {
        debounceMs: WATCH_DEBOUNCE_MS,
        ignore: [...(options.watchIgnoreGlobs ?? [])],
        onResync: () => this.emit([{ kind: 'resync' }]),
      }
    );
    this.watchReadyPromise = this.watch.ready().then((attached) => {
      if (attached.success) {
        this.emit([{ kind: 'resync' }]);
        return;
      }
      if (this.disposed) return;
      options.onError?.(`files root watch ${options.identity.rootId}`, attached.error);
    });
  }

  /**
   * Settles once the watch attach attempt finishes (never rejects). After a
   * successful attach a resync change has been emitted; after a failed attach
   * the resource keeps serving reads without live change notifications.
   */
  watchReady(): Promise<void> {
    return this.watchReadyPromise;
  }

  subscribe(listener: (changes: RootChange[]) => void): Unsubscribe {
    if (this.disposed) throw new Error('RootResource is disposed');
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  publishKnownChanges(changes: RootChange[]): void {
    const accepted = changes.flatMap((change): RootChange[] => {
      if (change.kind === 'resync') return [change];
      return normalizeRelativePath(change.path).success ? [change] : [];
    });
    this.emit(accepted);
  }

  runFileMutation<T>(resolvedPath: string, run: () => Promise<T>): Promise<T> {
    if (this.disposed) throw new Error('RootResource is disposed');
    return this.mutationMutex.runExclusive(resolvedPath, run);
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    this.listeners.clear();
    await this.watch.release();
  }

  private emit(changes: RootChange[]): void {
    if (this.disposed || changes.length === 0) return;
    for (const listener of [...this.listeners]) listener(changes);
  }
}
