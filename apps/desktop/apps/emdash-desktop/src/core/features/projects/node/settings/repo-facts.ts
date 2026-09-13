import type {
  GitRefsState,
  GitRemotesState,
  RepositorySelector,
} from '@emdash/core/runtimes/git/api';
import { branchNameOnRemote, gitContract, shortName } from '@emdash/core/runtimes/git/api';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { log } from '@emdash/shared/logger';
import { observe, remote, type Snapshot } from '@emdash/wire/state';
import type { RepoFactsSource } from '@core/features/projects/api/node/settings/effective-settings';
import type { RepoFacts, RepoRemoteFacts } from '@core/primitives/project-settings/api';
import { parseRepositoryRef } from '@core/primitives/repository/api';
import type { GitRuntimeClient } from '@core/services/runtime-broker/api/clients';

/**
 * The declared node-side repo-facts cache (spec: github-git-settings §2): one
 * per-project in-memory view over the git runtime's `remotes` and `refs` live
 * states — remotes with host and remote HEAD, remote branches, and local
 * branches. Reads never run git work; the underlying live states are computed
 * once and invalidated by the git events that already flow (fs watches on
 * `refs/**` and `config`, fetch/push/add-remote mutations).
 *
 * The subscription starts lazily on the first read and lives until `dispose`
 * (the project provider's release). A failed subscription answers `null`
 * ("facts unavailable — degrade/skip") and is torn down so the next read
 * retries instead of pinning the failure for the provider's lifetime.
 */
export function createRepoFactsCache(
  git: GitRuntimeClient,
  repository: RepositorySelector,
  hasRepository: boolean
): RepoFactsSource {
  if (!hasRepository) {
    return { get: () => Promise.resolve(null), dispose: () => Promise.resolve() };
  }

  let scope: Scope | undefined;
  let remotesSnapshot: Snapshot<GitRemotesState | undefined> | undefined;
  let refsSnapshot: Snapshot<GitRefsState | undefined> | undefined;
  let waiters: Array<() => void> = [];
  let disposed = false;

  const notify = () => {
    const pending = waiters;
    waiters = [];
    for (const resolve of pending) resolve();
  };

  const start = () => {
    const nextScope = createScope({ label: 'repo-facts-cache' });
    scope = nextScope;
    const model = remote(gitContract.repository.model, git.repository.model, { scope: nextScope });
    const { states } = model(repository);
    observe(
      states.remotes,
      (snapshot) => {
        remotesSnapshot = snapshot;
        notify();
      },
      { scope: nextScope }
    );
    observe(
      states.refs,
      (snapshot) => {
        refsSnapshot = snapshot;
        notify();
      },
      { scope: nextScope }
    );
  };

  const reset = () => {
    const current = scope;
    scope = undefined;
    remotesSnapshot = undefined;
    refsSnapshot = undefined;
    if (current) void current.dispose();
  };

  /** null = failed, undefined = still loading. */
  const current = (): RepoFacts | null | undefined => {
    if (!remotesSnapshot || !refsSnapshot) return undefined;
    if (remotesSnapshot.status === 'error' || refsSnapshot.status === 'error') return null;
    if (remotesSnapshot.value === undefined || refsSnapshot.value === undefined) return undefined;
    return buildRepoFacts(remotesSnapshot.value, refsSnapshot.value);
  };

  return {
    async get() {
      if (disposed) return null;
      if (!scope) start();
      for (;;) {
        const facts = current();
        if (facts === null) {
          log.warn('Repo-facts cache subscription failed; retrying on the next read', {
            repository,
            error: remotesSnapshot?.error ?? refsSnapshot?.error,
          });
          reset();
          return null;
        }
        if (facts !== undefined) return facts;
        if (disposed) return null;
        await new Promise<void>((resolve) => waiters.push(resolve));
      }
    },
    async dispose() {
      disposed = true;
      notify();
      const current = scope;
      scope = undefined;
      if (current) await current.dispose();
    },
  };
}

export function buildRepoFacts(remotesState: GitRemotesState, refsState: GitRefsState): RepoFacts {
  const branches = refsState.branches;
  const remoteHeads = refsState.remoteHeads;
  const remotes: RepoRemoteFacts[] = remotesState.remotes.map((remote) => ({
    name: remote.name,
    host: parseRepositoryRef(remote.url)?.host ?? null,
    headBranch: (() => {
      const head = remoteHeads.find((candidate) => candidate.remote === remote.name);
      return head ? branchNameOnRemote(head.ref, remote) : null;
    })(),
    branches: branches.flatMap((branch) =>
      branch.type === 'remote' && branch.remote.name === remote.name
        ? [branchNameOnRemote(branch.ref, branch.remote)]
        : []
    ),
  }));

  return {
    remotes,
    localBranches: branches.flatMap((branch) =>
      branch.type === 'local' ? [shortName(branch.ref)] : []
    ),
  };
}
