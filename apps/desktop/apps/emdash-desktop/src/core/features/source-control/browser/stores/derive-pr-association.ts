import type { WorkspaceObservedPrFacts } from '@core/primitives/tasks/api';
import { recognizePullRequestUrl, type PullRequest } from '@core/services/pull-requests/api';

/** Reads against the synced PR cache; lookup failures should reject, not return null. */
export type PrCacheLookups = {
  /** The cache's PR for a canonical PR URL, or null when the URL is unknown to it. */
  byUrl(url: string): Promise<PullRequest | null>;
  /** Today's head-branch match. */
  byBranch(branch: string): Promise<PullRequest[]>;
};

/**
 * Derives a task's PR association from observed facts, validated against the PR
 * cache on every read (pr-workspace-model spec, Association):
 *
 * 1. An observed breadcrumb that validates against the cache wins outright.
 * 2. Otherwise the gh-checkout convention (`refs/pull/N/head` + base remote URL) is
 *    recognized as an implicit breadcrumb and validated the same way.
 * 3. Otherwise head-branch matching — which therefore can never override a
 *    validated breadcrumb or convention association.
 *
 * An unvalidatable breadcrumb (unknown PR, unparseable URL) is ignored silently:
 * association self-corrects with no repair surface. Unobserved workspaces (old
 * hosts) fall straight to branch matching.
 */
export async function derivePrAssociation(input: {
  /** Mirror observedGit v2 facts; null (old host / v1) degrades to branch matching. */
  observed: WorkspaceObservedPrFacts | null;
  /** The git runtime's live branch; observed branch backs it up when absent. */
  checkoutBranch: string | null;
  lookups: PrCacheLookups;
}): Promise<PullRequest[]> {
  const { observed, lookups } = input;

  if (observed?.prBreadcrumb) {
    const pr = await lookups.byUrl(observed.prBreadcrumb);
    if (pr) return [pr];
  }

  const recognized = recognizePullRequestUrl(observed?.upstream ?? null);
  if (recognized && recognized !== observed?.prBreadcrumb) {
    const pr = await lookups.byUrl(recognized);
    if (pr) return [pr];
  }

  const branch = input.checkoutBranch ?? observed?.branch ?? null;
  if (!branch) return [];
  return await lookups.byBranch(branch);
}
