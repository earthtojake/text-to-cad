import type { GitBranchRef } from '@core/primitives/git/api';

export type BranchLabelRemoteMode = 'full' | 'short';

export function getBranchLabel(
  branch: GitBranchRef,
  options: { remote?: BranchLabelRemoteMode } = {}
): string {
  if (branch.type !== 'remote') return branch.branch;
  return options.remote === 'short' ? branch.branch : `${branch.remote.name}/${branch.branch}`;
}

export function filterBranchesForPicker(
  branches: ReadonlyArray<GitBranchRef>,
  tab: 'local' | 'remote',
  remoteName?: string
): GitBranchRef[] {
  return branches.filter(
    (branch) =>
      branch.type === tab &&
      (branch.type !== 'remote' || !remoteName || branch.remote.name === remoteName)
  );
}

export function prioritizeExactBranchMatches(
  branches: ReadonlyArray<GitBranchRef>,
  query: string,
  branchLabelRemote: BranchLabelRemoteMode = 'full'
): GitBranchRef[] {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return [...branches];

  return branches
    .map((branch, index) => ({
      branch,
      index,
      rank: getExactMatchRank(branch, normalizedQuery, branchLabelRemote),
    }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map(({ branch }) => branch);
}

function getExactMatchRank(
  branch: GitBranchRef,
  normalizedQuery: string,
  branchLabelRemote: BranchLabelRemoteMode
): number {
  if (branch.branch.toLocaleLowerCase() === normalizedQuery) return 0;
  if (
    getBranchLabel(branch, { remote: branchLabelRemote }).toLocaleLowerCase() === normalizedQuery
  ) {
    return 1;
  }
  return 2;
}
