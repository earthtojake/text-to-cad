import type { Result } from '@emdash/shared';
import type { GitResolutionError, GitSelector } from '#runtimes/git/api';

type Brand<Value, Name extends string> = Value & { readonly __brand: Name };

export type RepositoryId = Brand<string, 'git-common-dir'>;
export type ObjectStoreId = Brand<string, 'git-object-store'>;
export type CheckoutId = Brand<string, 'git-checkout-identity'>;

export type RepositoryIdentity = Readonly<{
  repositoryId: RepositoryId;
  objectStoreId: ObjectStoreId;
  gitCommonDir: string;
  objectStoreDir: string;
}>;

export type CheckoutIdentity = RepositoryIdentity &
  Readonly<{
    checkoutId: CheckoutId;
    checkoutRoot: string;
    gitDir: string;
  }>;

export type GitIdentityResolver = {
  resolve(selector: GitSelector): Promise<Result<CheckoutIdentity, GitResolutionError>>;
  dispose(): void;
};

export function repositoryIdentityOf(identity: CheckoutIdentity): RepositoryIdentity {
  return {
    repositoryId: identity.repositoryId,
    objectStoreId: identity.objectStoreId,
    gitCommonDir: identity.gitCommonDir,
    objectStoreDir: identity.objectStoreDir,
  };
}
