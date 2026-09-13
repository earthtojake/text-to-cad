import { ok, type Result } from '@emdash/shared';
import type { HostAbsolutePath } from '#primitives/path/api';
import { gitErr, type GitResolutionError, type GitSelector } from '#runtimes/git/api';
import { gitFailure } from '#runtimes/git/node/exec/errors';
import type { BoundExec } from '#services/exec/api';
import type {
  CheckoutId,
  CheckoutIdentity,
  GitIdentityResolver,
  ObjectStoreId,
  RepositoryId,
} from './identity';
import { realpathOrResolve, toNativeAbsolutePath } from './paths';

export type CanonicalGitIdentityResolverOptions = Readonly<{
  exec: BoundExec;
  aliasTtlMs?: number;
}>;

type AliasEntry = {
  promise: Promise<Result<CheckoutIdentity, GitResolutionError>>;
  timer?: ReturnType<typeof setTimeout>;
};

const DEFAULT_ALIAS_TTL_MS = 30_000;

/** Resolves user path aliases once, sharing concurrent rev-parse work. */
export class CanonicalGitIdentityResolver implements GitIdentityResolver {
  private readonly entries = new Map<string, AliasEntry>();
  private readonly aliasTtlMs: number;
  private disposed = false;

  constructor(private readonly options: CanonicalGitIdentityResolverOptions) {
    this.aliasTtlMs = options.aliasTtlMs ?? DEFAULT_ALIAS_TTL_MS;
  }

  resolve(selector: GitSelector): Promise<Result<CheckoutIdentity, GitResolutionError>> {
    if (this.disposed) return Promise.reject(new Error('GitIdentityResolver is disposed'));
    const requestedPath = selectorPath(selector);
    let alias: string;
    try {
      alias = toNativeAbsolutePath(requestedPath);
    } catch (error) {
      return Promise.resolve(
        gitErr.resolutionFailed(
          requestedPath,
          error instanceof Error ? error.message : String(error)
        )
      );
    }
    const existing = this.entries.get(alias);
    if (existing) {
      this.armExpiry(alias, existing);
      return existing.promise;
    }

    const entry: AliasEntry = { promise: this.resolveAlias(alias, requestedPath) };
    this.entries.set(alias, entry);
    this.armExpiry(alias, entry);
    void entry.promise.then(
      (result) => {
        if (!result.success && this.entries.get(alias) === entry) this.deleteEntry(alias, entry);
      },
      () => this.deleteEntry(alias, entry)
    );
    return entry.promise;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    for (const entry of this.entries.values()) {
      if (entry.timer) clearTimeout(entry.timer);
    }
    this.entries.clear();
  }

  private async resolveAlias(
    alias: string,
    requestedPath: HostAbsolutePath
  ): Promise<Result<CheckoutIdentity, GitResolutionError>> {
    const exec = this.options.exec.withCwd(alias);
    try {
      const [checkoutRoot, gitDir, gitCommonDir, objectStoreDir] = await Promise.all([
        exec.exec(['rev-parse', '--show-toplevel']).then(({ stdout }) => stdout.trim()),
        exec
          .exec(['rev-parse', '--path-format=absolute', '--git-dir'])
          .then(({ stdout }) => stdout.trim()),
        exec
          .exec(['rev-parse', '--path-format=absolute', '--git-common-dir'])
          .then(({ stdout }) => stdout.trim()),
        exec
          .exec(['rev-parse', '--path-format=absolute', '--git-path', 'objects'])
          .then(({ stdout }) => stdout.trim()),
      ]);
      if (!checkoutRoot || !gitDir || !gitCommonDir || !objectStoreDir) {
        return gitErr.resolutionFailed(requestedPath, 'Incomplete Git identity');
      }

      const canonicalCheckoutRoot = realpathOrResolve(checkoutRoot);
      const canonicalGitDir = realpathOrResolve(gitDir);
      const canonicalCommonDir = realpathOrResolve(gitCommonDir);
      const canonicalObjectStore = realpathOrResolve(objectStoreDir);
      return ok({
        repositoryId: canonicalCommonDir as RepositoryId,
        objectStoreId: canonicalObjectStore as ObjectStoreId,
        checkoutId: JSON.stringify([canonicalCheckoutRoot, canonicalGitDir]) as CheckoutId,
        checkoutRoot: canonicalCheckoutRoot,
        gitDir: canonicalGitDir,
        gitCommonDir: canonicalCommonDir,
        objectStoreDir: canonicalObjectStore,
      });
    } catch (error) {
      return gitErr.resolutionFailed(requestedPath, gitFailure(error).message);
    }
  }

  private armExpiry(alias: string, entry: AliasEntry): void {
    if (entry.timer) clearTimeout(entry.timer);
    if (this.aliasTtlMs <= 0) return;
    entry.timer = setTimeout(() => this.deleteEntry(alias, entry), this.aliasTtlMs);
    entry.timer.unref?.();
  }

  private deleteEntry(alias: string, entry: AliasEntry): void {
    if (this.entries.get(alias) !== entry) return;
    if (entry.timer) clearTimeout(entry.timer);
    this.entries.delete(alias);
  }
}

function selectorPath(selector: GitSelector): HostAbsolutePath {
  return 'repository' in selector ? selector.repository : selector.checkout;
}
