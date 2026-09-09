import { err, ok, type Result } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import { type LiveJobContext } from '@emdash/wire/live';
import { type LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { expose, type Query } from '@emdash/wire/state';
import {
  gitContract,
  type gitRepositoryContract,
  type FetchJobInput,
  type FetchPrForReviewJobInput,
  type GitCommandError,
  type GitRefsState,
  type GitRemotesState,
  type GitTransferProgress,
  type RepositorySelector,
} from '#runtimes/git/api';
import type { GitAllocationGraph } from '#runtimes/git/node/allocation/allocation-graph';
import { expectedGitCommandError } from '#runtimes/git/node/api/errors';
import { credentialOperationEnv } from '#runtimes/git/node/exec/operation-context';
import type { RepositoryResource } from './repository-resource';

type RepositoryModel = typeof gitRepositoryContract.model;
type RepositoryStateName = 'refs' | 'remotes';

export class GitRepositoryRuntime {
  readonly model: LeasedLiveModelProvider<RepositoryModel>;

  private readonly modelHosts = new Map<string, LeasedLiveModelProvider<RepositoryModel>>();

  constructor(private readonly allocations: GitAllocationGraph) {
    this.model = this.modelHost(gitContract.repository.model);
  }

  modelHost(contract: RepositoryModel = gitContract.repository.model) {
    const existing = this.modelHosts.get(contract.id);
    if (existing) return existing;
    const host = expose(
      contract,
      {
        refs: (key, scope) => this.repositoryState<GitRefsState>(key, 'refs', scope),
        remotes: (key, scope) => this.repositoryState<GitRemotesState>(key, 'remotes', scope),
      },
      {
        mutations: {
          addRemote: (context) => this.run(context.key, (resource) => resource.addRemote(context)),
        },
      }
    );
    this.modelHosts.set(contract.id, host);
    return host;
  }

  listWorktrees(input: RepositorySelector) {
    return this.read(input, async (repository) => ({
      worktrees: await repository.listWorktrees(),
    }));
  }

  getDefaultBranch(input: RepositorySelector & { remote: string }) {
    return this.read(input, async (repository) => ({
      branch: await repository.getDefaultBranch(input.remote),
    }));
  }

  fetch(input: FetchJobInput, context: LiveJobContext<GitTransferProgress>) {
    return this.run(input, (repository) =>
      repository.fetch(
        input.remote,
        {
          signal: context.signal,
          onProgress: context.progress,
          env: credentialOperationEnv(input.credentials),
        },
        {
          refspec: input.refspec,
          force: input.force,
        }
      )
    );
  }

  fetchPrForReview(input: FetchPrForReviewJobInput, context: LiveJobContext<GitTransferProgress>) {
    return this.run(input, (repository) =>
      repository.fetchPrForReview(input.options, {
        signal: context.signal,
        onProgress: context.progress,
        env: credentialOperationEnv(input.credentials),
      })
    );
  }

  async dispose(): Promise<void> {
    await Promise.all([...this.modelHosts.values()].map((host) => host.dispose()));
    this.modelHosts.clear();
  }

  private read<T>(
    selector: RepositorySelector,
    read: (resource: RepositoryResource) => Promise<T>
  ) {
    return this.run(
      selector,
      async (resource): Promise<Result<T, never>> => ok(await read(resource))
    );
  }

  private async repositoryState<T>(
    selector: RepositorySelector,
    name: RepositoryStateName,
    scope: Scope
  ): Promise<Query<T>> {
    const lease = this.allocations.acquireRepository(selector);
    scope.add(() => lease.release());
    const repository = await lease.ready();
    switch (name) {
      case 'refs':
        return repository.state('refs') as unknown as Query<T>;
      case 'remotes':
        return repository.state('remotes') as unknown as Query<T>;
    }
  }

  private async run<T, E>(
    selector: RepositorySelector,
    run: (resource: RepositoryResource) => Promise<Result<T, E>>
  ): Promise<Result<T, E | GitCommandError>> {
    try {
      return await this.allocations.useRepository(selector, run);
    } catch (error) {
      const expected = expectedGitCommandError(error);
      if (expected) return err(expected);
      throw error;
    }
  }
}
