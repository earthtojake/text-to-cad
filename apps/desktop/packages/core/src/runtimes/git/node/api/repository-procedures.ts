import type { ContractImpl } from '@emdash/wire/rpc';
import type { GitContract } from '#runtimes/git/api';
import type { GitRepositoryRuntime } from '#runtimes/git/node/repository/repository-runtime';

type RepositoryImplementation = NonNullable<ContractImpl<GitContract>['repository']>;

export function createRepositoryProcedures(runtime: GitRepositoryRuntime) {
  return {
    listWorktrees: (input) => runtime.listWorktrees(input),
    getDefaultBranch: (input) => runtime.getDefaultBranch(input),
    fetch: { run: (input, context) => runtime.fetch(input, context) },
    fetchPrForReview: { run: (input, context) => runtime.fetchPrForReview(input, context) },
  } satisfies Omit<RepositoryImplementation, 'model'>;
}
