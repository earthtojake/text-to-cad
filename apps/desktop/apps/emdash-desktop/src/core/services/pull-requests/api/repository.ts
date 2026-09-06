import { parseRepositoryRef } from '@core/primitives/repository/api';
import type { PullRequest } from './schemas';

export function normalizeRepositoryUrl(repositoryUrl: string): string | null {
  return parseRepositoryRef(repositoryUrl)?.repositoryUrl ?? null;
}

const ghPrMergeRefPattern = /^refs\/pull\/(\d+)\/head$/;

/**
 * Recognizes gh CLI's PR checkout convention as an implicit PR breadcrumb
 * (pr-workspace-model spec, Association): `branch.<b>.merge = refs/pull/N/head`
 * with the base remote's URL constructs the canonical PR URL — the PR cache's key.
 * Provider knowledge stays desktop-side; the host only reports the raw config
 * values. Returns null for anything that is not the convention (callers fall back
 * to branch matching); GitLab's `refs/merge-requests/N/head` is a later addition.
 */
export function recognizePullRequestUrl(
  upstream: { mergeRef: string; remoteUrl: string | null } | null
): string | null {
  if (!upstream?.remoteUrl) return null;
  const match = ghPrMergeRefPattern.exec(upstream.mergeRef);
  if (!match) return null;
  const repositoryUrl = normalizeRepositoryUrl(upstream.remoteUrl);
  if (!repositoryUrl) return null;
  return `${repositoryUrl}/pull/${match[1]}`;
}

export function selectCurrentPr(pullRequests: readonly PullRequest[]): PullRequest | undefined {
  const open = pullRequests.find((pullRequest) => pullRequest.status === 'open');
  if (open) return open;
  return pullRequests.reduce<PullRequest | undefined>(
    (latest, pullRequest) =>
      !latest || pullRequest.createdAt > latest.createdAt ? pullRequest : latest,
    undefined
  );
}

export function isForkPr(
  pullRequest: Pick<PullRequest, 'headRepositoryUrl' | 'repositoryUrl'>
): boolean {
  return pullRequest.headRepositoryUrl !== pullRequest.repositoryUrl;
}

export function getPrNumber(pullRequest: { identifier: string | null }): number | null {
  if (!pullRequest.identifier) return null;
  const number = Number.parseInt(pullRequest.identifier.replace('#', ''), 10);
  return Number.isNaN(number) ? null : number;
}
