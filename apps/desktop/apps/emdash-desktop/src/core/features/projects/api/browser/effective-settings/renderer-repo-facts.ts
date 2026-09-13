import {
  branchNameOnRemote,
  shortName,
  type GitBranch,
  type GitRemote,
  type GitRemoteHead,
} from '@emdash/core/runtimes/git/api';
import type { RepoFacts, RepoRemoteFacts } from '@core/primitives/project-settings/api';
import { parseRepositoryRef } from '@core/primitives/repository/api';

/**
 * Maps the synced repository live model (`GitRepositoryStore` data) to the
 * blessed resolver's `RepoFacts` (spec: github-git-settings §2). Mirrors the
 * node-side loader (`features/projects/node/settings/repo-facts.ts`): remote
 * HEADs come from the refs state's `refs/remotes/<remote>/HEAD` symbolic refs.
 * When a remote's HEAD is unknown the resolver degrades to the well-known
 * branch candidates.
 */
export function buildRendererRepoFacts(args: {
  remotes: GitRemote[];
  branches: GitBranch[];
  remoteHeads: GitRemoteHead[];
}): RepoFacts {
  const { remotes, branches, remoteHeads } = args;
  const remoteFacts: RepoRemoteFacts[] = remotes.map((remote) => ({
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
    remotes: remoteFacts,
    localBranches: branches.flatMap((branch) =>
      branch.type === 'local' ? [shortName(branch.ref)] : []
    ),
  };
}
