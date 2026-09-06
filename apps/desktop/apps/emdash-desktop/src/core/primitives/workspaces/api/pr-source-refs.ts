/**
 * The PR-preset source-ref vocabulary (pr-workspace-model spec, per-case
 * compilation), defined once: the worktree git-plan compiler and the manual-update
 * instruction compiler share these strings, so provisioning and updating can never
 * disagree about where a PR checkout's commits come from. Provider knowledge
 * (GitHub's `refs/pull/<N>/head` convention) stays desktop-side by design — the host
 * contract only ever sees plain git refs.
 */

/** The forge's read-only PR head ref, fetchable from the base remote for any origin. */
export function prHeadRef(prNumber: number): string {
  return `refs/pull/${prNumber}/head`;
}

export function branchHeadRef(branch: string): string {
  return `refs/heads/${branch}`;
}

/**
 * The per-case checkout source: same-repo PRs track the real head branch
 * (commit-and-push preserved); fork PRs the PR ref (review-first — the forge itself
 * rejects pushes).
 */
export function prCheckoutSourceRef(input: {
  prNumber: number;
  headBranch: string;
  isFork: boolean;
}): string {
  return input.isFork ? prHeadRef(input.prNumber) : branchHeadRef(input.headBranch);
}
