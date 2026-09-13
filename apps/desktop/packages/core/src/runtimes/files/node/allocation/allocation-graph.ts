import { toPendingLease, type Lease, type PendingLease, type Result } from '@emdash/shared';
import { createResourceCache, type ResourceCache } from '@emdash/shared/concurrency';
import type { PortableRelativePath } from '#primitives/path/api';
import type { AbsolutePathKey, ContentKey, FsError, RootKey, TreeKey } from '#runtimes/files/api';
import { FsException } from '#runtimes/files/node/api/errors';
import { ContentResource } from '#runtimes/files/node/content/content-resource';
import {
  RootResource,
  type AbsoluteChange,
  type RootChange,
} from '#runtimes/files/node/root/root-resource';
import { TreeResource } from '#runtimes/files/node/tree/tree-resource';
import type { IWatchService } from '#services/fs-watch/api';
import {
  contentIdentity,
  resolveAbsoluteFileLocation,
  resolveRootIdentity,
  treeIdentity,
  type RootIdentity,
  type TreeIdentity,
  type ContentIdentity,
} from './identity';

const DEFAULT_IDLE_TTL_MS = 30_000;

// A children-scoped parent watch only serves per-file content updates, so events
// beneath direct subdirectories are ignored at the native watcher.
const CHILDREN_WATCH_IGNORE: readonly string[] = ['*/**'];

export type FilesAllocationGraphOptions = {
  watcher: IWatchService;
  watchIgnoreGlobs?: readonly string[];
  idleTtlMs?: number;
  maxContentBytes?: number;
  onError?: (context: string, error: unknown) => void;
};

export class FilesAllocationGraph {
  private readonly roots: ResourceCache<RootIdentity, RootResource>;
  private readonly trees: ResourceCache<TreeIdentity, TreeResource>;
  private readonly contents: ResourceCache<ContentIdentity, ContentResource>;
  private readonly activeRoots = new Set<RootResource>();
  private readonly activeTrees = new Set<TreeResource>();
  private readonly onError: (context: string, error: unknown) => void;
  private disposed = false;

  constructor(options: FilesAllocationGraphOptions) {
    const idleTtlMs = options.idleTtlMs ?? DEFAULT_IDLE_TTL_MS;
    const onError = options.onError ?? (() => {});
    this.onError = onError;
    this.roots = createResourceCache({
      key: (identity: RootIdentity) => identity.rootId,
      idleTtlMs,
      onError: (error, id) => onError(`files root ${id}`, error),
      create: async (identity, scope) => {
        const resource = await RootResource.create({
          identity,
          watcher: options.watcher,
          watchIgnoreGlobs:
            identity.watchScope === 'children' ? CHILDREN_WATCH_IGNORE : options.watchIgnoreGlobs,
          onError,
        });
        scope.add(() => resource.dispose());
        this.activeRoots.add(resource);
        scope.add(() => {
          this.activeRoots.delete(resource);
        });
        return resource;
      },
    });
    this.trees = createResourceCache({
      key: (identity: TreeIdentity) => identity.treeId,
      idleTtlMs,
      onError: (error, id) => onError(`files tree ${id}`, error),
      create: async (identity, scope) => {
        const rootLease = this.roots.acquire(identity.root);
        scope.add(() => rootLease.release());
        const resource = new TreeResource({
          identity,
          root: await rootLease.ready(),
          onError,
        });
        scope.add(() => resource.dispose());
        this.activeTrees.add(resource);
        scope.add(() => {
          this.activeTrees.delete(resource);
        });
        return resource;
      },
    });
    this.contents = createResourceCache({
      key: (identity: ContentIdentity) => identity.contentId,
      idleTtlMs,
      onError: (error, id) => onError(`files content ${id}`, error),
      create: async (identity, scope) => {
        const rootLease = this.roots.acquire(identity.root);
        scope.add(() => rootLease.release());
        const resource = new ContentResource({
          identity,
          root: await rootLease.ready(),
          maxBytes: options.maxContentBytes,
          onError,
        });
        scope.add(() => resource.dispose());
        return resource;
      },
    });
  }

  acquireTree(key: TreeKey): PendingLease<TreeResource> {
    return this.acquireResolved(resolveRootIdentity(key.root), (root) =>
      this.trees.acquire(treeIdentity(root, key))
    );
  }

  /**
   * Content sessions are keyed by a bare host-absolute path and always
   * per-file watched: the key resolves to the file's canonical parent
   * directory as a children-scoped root, whose watch serves the session's
   * live updates — whether or not the file sits under any registered root.
   */
  acquireContent(key: ContentKey): PendingLease<ContentResource> {
    return this.acquireResolved(resolveAbsoluteFileLocation(key.path), ({ root, relative }) =>
      this.contents.acquire(contentIdentity(root, relative))
    );
  }

  acquireRoot(key: RootKey): PendingLease<RootResource> {
    return this.acquireResolved(resolveRootIdentity(key.root), (identity) =>
      this.roots.acquire(identity)
    );
  }

  async useRoot<T>(key: RootKey, run: (root: RootResource) => Promise<T>): Promise<T> {
    const lease = this.acquireRoot(key);
    try {
      return await run(await lease.ready());
    } finally {
      await lease.release();
    }
  }

  /**
   * Runs an operation against the operational root resource and root-relative
   * path an absolute file key resolves to: the file's canonical parent
   * directory plus the file name.
   */
  async useFileLocation<T>(
    key: AbsolutePathKey,
    run: (root: RootResource, relative: PortableRelativePath) => Promise<T>
  ): Promise<T> {
    const location = await resolveAbsoluteFileLocation(key.path);
    if (!location.success) throw new FsException(location.error);
    this.assertActive();
    const lease = this.roots.acquire(location.data.root);
    try {
      return await run(await lease.ready(), location.data.relative);
    } finally {
      await lease.release();
    }
  }

  notifyActiveRoot(root: RootResource, changes: RootChange[]): void {
    root.publishKnownChanges(changes);
  }

  /**
   * Reflects a successful stateless fs mutation into the rest of the graph
   * before the mutation acks (spec §3.4) — the fs watcher covers external
   * changes only. Changes are published into every other active root
   * subscription (content and tree listeners react on their usual async
   * paths), and affected live tree sessions are additionally reconciled
   * synchronously so their state reflects the mutation by ack time. Republish
   * failures are reported, not propagated: the disk mutation already
   * succeeded.
   */
  async reflectMutation(origins: RootResource[], changes: AbsoluteChange[]): Promise<void> {
    if (changes.length === 0) return;
    for (const root of this.activeRoots) {
      if (origins.includes(root)) continue;
      const relative = changes.flatMap((change): RootChange[] => {
        const path = root.paths.toRelative(change.absolutePath);
        return path === null ? [] : [{ kind: change.kind, path }];
      });
      if (relative.length > 0) root.publishKnownChanges(relative);
    }
    await Promise.all(
      [...this.activeTrees].map((tree) =>
        tree.applyAbsoluteChanges(changes).catch((error: unknown) => {
          this.onError(`files tree republish ${tree.identity.treeId}`, error);
        })
      )
    );
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    await this.contents.dispose();
    await this.trees.dispose();
    await this.roots.dispose();
  }

  private acquireResolved<Resolved, Resource>(
    resolved: Promise<Result<Resolved, FsError>>,
    acquire: (value: Resolved) => PendingLease<Resource>
  ): PendingLease<Resource> {
    this.assertActive();
    return toPendingLease(
      resolved.then(async (result): Promise<Lease<Resource>> => {
        if (!result.success) throw new FsException(result.error);
        const resourceLease = acquire(result.data);
        try {
          return {
            value: await resourceLease.ready(),
            release: () => resourceLease.release(),
          };
        } catch (error) {
          await resourceLease.release();
          throw error;
        }
      })
    );
  }

  private assertActive(): void {
    if (this.disposed) throw new Error('FilesAllocationGraph is disposed');
  }
}
