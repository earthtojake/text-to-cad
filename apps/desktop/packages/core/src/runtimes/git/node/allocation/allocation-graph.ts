import { toPendingLease, type Lease, type PendingLease, type Result } from '@emdash/shared';
import { createResourceCache, type ResourceCache } from '@emdash/shared/concurrency';
import { KeyedMutex } from '@emdash/shared/concurrency';
import type { CheckoutSelector, GitResolutionError, RepositorySelector } from '#runtimes/git/api';
import { CheckoutResource } from '#runtimes/git/node/checkout/checkout-resource';
import { GitCheckout } from '#runtimes/git/node/checkout/git-checkout';
import { bindGitDir } from '#runtimes/git/node/exec/git-exec';
import { GitRepository } from '#runtimes/git/node/repository/git-repository';
import { RepositoryResource } from '#runtimes/git/node/repository/repository-resource';
import type { BoundExec } from '#services/exec/api';
import type { IWatchService } from '#services/fs-watch/api';
import {
  repositoryIdentityOf,
  type CheckoutIdentity,
  type GitIdentityResolver,
  type RepositoryIdentity,
} from './identity';
import { CanonicalGitIdentityResolver } from './identity-resolver';

const DEFAULT_IDLE_TTL_MS = 30_000;

export type GitAllocationGraphOptions = Readonly<{
  exec: BoundExec;
  watcher: IWatchService;
  identityResolver?: GitIdentityResolver;
  objectStoreMutex?: KeyedMutex;
  idleTtlMs?: number;
  aliasTtlMs?: number;
  maxFileContentStates?: number;
  onError?: (context: string, error: unknown) => void;
}>;

export class GitResolutionException extends Error {
  constructor(readonly resolution: GitResolutionError) {
    super(resolution.message);
    this.name = 'GitResolutionException';
  }
}

/** Private registry for canonical repository and checkout resources. */
export class GitAllocationGraph {
  private readonly resolver: GitIdentityResolver;
  private readonly ownsResolver: boolean;
  private readonly repositories: ResourceCache<RepositoryIdentity, RepositoryResource>;
  private readonly checkouts: ResourceCache<CheckoutIdentity, CheckoutResource>;
  private disposed = false;

  constructor(private readonly options: GitAllocationGraphOptions) {
    const idleTtlMs = options.idleTtlMs ?? DEFAULT_IDLE_TTL_MS;
    const objectStoreMutex = options.objectStoreMutex ?? new KeyedMutex();
    const onError = options.onError ?? (() => {});
    this.ownsResolver = !options.identityResolver;
    this.resolver =
      options.identityResolver ??
      new CanonicalGitIdentityResolver({ exec: options.exec, aliasTtlMs: options.aliasTtlMs });

    this.repositories = createResourceCache({
      key: (identity: RepositoryIdentity) => identity.repositoryId,
      idleTtlMs,
      onError: (error, id) => onError(`git repository ${id}`, error),
      create: async (identity, scope) => {
        const commands = new GitRepository({
          identity,
          exec: bindGitDir(options.exec, identity.gitCommonDir),
        });
        const resource = await RepositoryResource.create({
          identity,
          commands,
          watcher: options.watcher,
          objectStoreMutex,
          onError,
        });
        scope.add(() => resource.dispose());
        return resource;
      },
    });

    this.checkouts = createResourceCache({
      key: (identity: CheckoutIdentity) => identity.checkoutId,
      idleTtlMs,
      onError: (error, id) => onError(`git checkout ${id}`, error),
      create: async (identity, scope) => {
        const repositoryLease = this.repositories.acquire(repositoryIdentityOf(identity));
        scope.add(() => repositoryLease.release());
        const repository = await repositoryLease.ready();
        const commands = new GitCheckout({
          identity,
          exec: options.exec.withCwd(identity.checkoutRoot),
        });
        const resource = await CheckoutResource.create({
          identity,
          commands,
          repository,
          watcher: options.watcher,
          maxFileContentStates: options.maxFileContentStates,
          onError,
        });
        scope.add(() => resource.dispose());
        return resource;
      },
    });
  }

  acquireRepository(selector: RepositorySelector): PendingLease<RepositoryResource> {
    return this.acquireResolved(this.resolver.resolve(selector), (identity) =>
      this.repositories.acquire(repositoryIdentityOf(identity))
    );
  }

  acquireCheckout(selector: CheckoutSelector): PendingLease<CheckoutResource> {
    return this.acquireResolved(this.resolver.resolve(selector), (identity) =>
      this.checkouts.acquire(identity)
    );
  }

  async useRepository<T>(
    selector: RepositorySelector,
    run: (resource: RepositoryResource) => Promise<T>
  ): Promise<T> {
    return this.use(this.acquireRepository(selector), run);
  }

  async useCheckout<T>(
    selector: CheckoutSelector,
    run: (resource: CheckoutResource) => Promise<T>
  ): Promise<T> {
    return this.use(this.acquireCheckout(selector), run);
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    await this.checkouts.dispose();
    await this.repositories.dispose();
    if (this.ownsResolver) this.resolver.dispose();
  }

  private acquireResolved<Resource>(
    resolved: Promise<Result<CheckoutIdentity, GitResolutionError>>,
    acquire: (identity: CheckoutIdentity) => PendingLease<Resource>
  ): PendingLease<Resource> {
    this.assertActive();
    return toPendingLease(
      resolved.then(async (result): Promise<Lease<Resource>> => {
        if (!result.success) throw new GitResolutionException(result.error);
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

  private async use<Resource, T>(
    lease: PendingLease<Resource>,
    run: (resource: Resource) => Promise<T>
  ): Promise<T> {
    try {
      return await run(await lease.ready());
    } finally {
      await lease.release();
    }
  }

  private assertActive(): void {
    if (this.disposed) throw new Error('GitAllocationGraph is disposed');
  }
}
