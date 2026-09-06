import type { GitBranchRef } from '@emdash/core/runtimes/git/api';

export function toShortBranchName(
  baseRef: string | undefined,
  branches: GitBranchRef[]
): string | undefined {
  const trimmed = baseRef?.trim();
  if (!trimmed) return undefined;

  if (branches.some((branch) => branch.branch === trimmed)) {
    return trimmed;
  }

  const knownRemotes = new Set(
    branches
      .filter(
        (branch): branch is Extract<GitBranchRef, { type: 'remote' }> => branch.type === 'remote'
      )
      .map((branch) => branch.remote.name)
      .filter(Boolean)
  );

  for (const remote of knownRemotes) {
    const prefix = `${remote}/`;
    if (trimmed.startsWith(prefix)) {
      const candidate = trimmed.slice(prefix.length);
      if (candidate && branches.some((branch) => branch.branch === candidate)) {
        return candidate;
      }
    }
  }

  return trimmed;
}

export function resolveInitialBaseBranch(
  branches: GitBranchRef[],
  preferredBase: GitBranchRef | undefined,
  defaultBranch: GitBranchRef | undefined,
  /** The effective base remote; null (no remotes) matches no remote branches. */
  projectRemoteName: string | null
): GitBranchRef | undefined {
  const projectRemoteBranches = branches.filter(
    (branch) => branch.type === 'remote' && branch.remote.name === projectRemoteName
  );
  const preferredName = preferredBase?.branch;
  if (preferredName) {
    if (preferredBase?.type === 'remote' && preferredBase.remote.name === projectRemoteName) {
      const preferredRemote = projectRemoteBranches.find(
        (branch) => branch.branch === preferredName
      );
      if (preferredRemote) return preferredRemote;
    }

    const preferredLocal = branches.find(
      (branch) => branch.type === 'local' && branch.branch === preferredName
    );
    if (preferredLocal) return preferredLocal;

    const preferredRemote = projectRemoteBranches.find((branch) => branch.branch === preferredName);
    if (preferredRemote) return preferredRemote;
  }

  if (!defaultBranch) return undefined;
  if (defaultBranch.type === 'remote') {
    return projectRemoteBranches.find((branch) => branch.branch === defaultBranch.branch);
  }

  return (
    branches.find((branch) => branch.type === 'local' && branch.branch === defaultBranch.branch) ??
    projectRemoteBranches.find((branch) => branch.branch === defaultBranch.branch)
  );
}
