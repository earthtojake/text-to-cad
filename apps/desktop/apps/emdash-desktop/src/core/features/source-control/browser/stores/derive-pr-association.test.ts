import { describe, expect, it, vi } from 'vitest';
import type { WorkspaceObservedPrFacts } from '@core/primitives/tasks/api';
import type { PullRequest } from '@core/services/pull-requests/api';
import { derivePrAssociation, type PrCacheLookups } from './derive-pr-association';

const repositoryUrl = 'https://github.com/emdash/emdash';

function observedFixture(
  overrides: Partial<WorkspaceObservedPrFacts> = {}
): WorkspaceObservedPrFacts {
  return {
    branch: null,
    prBreadcrumb: null,
    upstream: null,
    headOid: null,
    ahead: null,
    behind: null,
    ...overrides,
  };
}

function pullRequestFixture(overrides: Partial<PullRequest> = {}): PullRequest {
  return {
    url: `${repositoryUrl}/pull/1`,
    provider: 'github',
    repositoryUrl,
    baseRefName: 'main',
    baseRefOid: 'base',
    headRepositoryUrl: repositoryUrl,
    headRefName: 'feature',
    headRefOid: 'head',
    identifier: '#1',
    title: 'Feature',
    description: null,
    status: 'open',
    isDraft: false,
    additions: 10,
    deletions: 2,
    changedFiles: 1,
    commitCount: 1,
    mergeableStatus: 'MERGEABLE',
    mergeStateStatus: 'CLEAN',
    reviewDecision: null,
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-02T00:00:00.000Z',
    author: null,
    labels: [],
    assignees: [],
    checks: [],
    ...overrides,
  };
}

function cacheOf(prs: PullRequest[]): PrCacheLookups {
  return {
    byUrl: vi.fn(async (url: string) => prs.find((pr) => pr.url === url) ?? null),
    byBranch: vi.fn(async (branch: string) => prs.filter((pr) => pr.headRefName === branch)),
  };
}

describe('derivePrAssociation', () => {
  it('associates through a validated breadcrumb even when the branch differs (pr-new-branch)', async () => {
    const pr = pullRequestFixture({ url: `${repositoryUrl}/pull/42`, headRefName: 'their-branch' });
    const lookups = cacheOf([pr]);

    const prs = await derivePrAssociation({
      observed: observedFixture({
        branch: 'my-task-branch',
        prBreadcrumb: `${repositoryUrl}/pull/42`,
      }),
      checkoutBranch: 'my-task-branch',
      lookups,
    });

    expect(prs).toEqual([pr]);
    expect(lookups.byBranch).not.toHaveBeenCalled();
  });

  it('never lets branch matching override a validated breadcrumb', async () => {
    const breadcrumbPr = pullRequestFixture({
      url: `${repositoryUrl}/pull/42`,
      headRefName: 'their-branch',
    });
    const branchPr = pullRequestFixture({
      url: `${repositoryUrl}/pull/43`,
      headRefName: 'shared-branch',
    });
    const lookups = cacheOf([breadcrumbPr, branchPr]);

    const prs = await derivePrAssociation({
      observed: observedFixture({
        branch: 'shared-branch',
        prBreadcrumb: breadcrumbPr.url,
      }),
      checkoutBranch: 'shared-branch',
      lookups,
    });

    expect(prs).toEqual([breadcrumbPr]);
    expect(lookups.byBranch).not.toHaveBeenCalled();
  });

  it('silently ignores a breadcrumb the cache cannot validate and falls back to branch matching', async () => {
    const pr = pullRequestFixture({ headRefName: 'feature' });
    const lookups = cacheOf([pr]);

    const prs = await derivePrAssociation({
      observed: observedFixture({
        branch: 'feature',
        prBreadcrumb: `${repositoryUrl}/pull/9999`,
      }),
      checkoutBranch: 'feature',
      lookups,
    });

    expect(prs).toEqual([pr]);
  });

  it('recognizes gh pr checkout worktrees through the upstream convention', async () => {
    const pr = pullRequestFixture({ url: `${repositoryUrl}/pull/7`, headRefName: 'contrib' });
    const lookups = cacheOf([pr]);

    const prs = await derivePrAssociation({
      observed: observedFixture({
        branch: 'contrib',
        upstream: {
          mergeRef: 'refs/pull/7/head',
          remoteUrl: 'git@github.com:emdash/emdash.git',
        },
      }),
      checkoutBranch: 'contrib',
      lookups,
    });

    expect(prs).toEqual([pr]);
    expect(lookups.byBranch).not.toHaveBeenCalled();
  });

  it('does not treat ordinary branch upstreams as PR conventions', async () => {
    const pr = pullRequestFixture({ headRefName: 'feature' });
    const lookups = cacheOf([pr]);

    const prs = await derivePrAssociation({
      observed: observedFixture({
        branch: 'feature',
        upstream: {
          mergeRef: 'refs/heads/feature',
          remoteUrl: 'https://github.com/emdash/emdash',
        },
      }),
      checkoutBranch: 'feature',
      lookups,
    });

    expect(prs).toEqual([pr]);
    expect(lookups.byUrl).not.toHaveBeenCalled();
  });

  it('falls all the way through when neither breadcrumb nor convention validates', async () => {
    const lookups = cacheOf([]);

    const prs = await derivePrAssociation({
      observed: observedFixture({
        branch: 'feature',
        prBreadcrumb: `${repositoryUrl}/pull/1`,
        upstream: {
          mergeRef: 'refs/pull/2/head',
          remoteUrl: 'https://github.com/emdash/emdash',
        },
      }),
      checkoutBranch: 'feature',
      lookups,
    });

    expect(prs).toEqual([]);
    expect(lookups.byUrl).toHaveBeenCalledWith(`${repositoryUrl}/pull/1`);
    expect(lookups.byUrl).toHaveBeenCalledWith(`${repositoryUrl}/pull/2`);
    expect(lookups.byBranch).toHaveBeenCalledWith('feature');
  });

  it('does not re-validate a recognized URL identical to the failed breadcrumb', async () => {
    const lookups = cacheOf([]);

    await derivePrAssociation({
      observed: observedFixture({
        branch: 'feature',
        prBreadcrumb: `${repositoryUrl}/pull/5`,
        upstream: {
          mergeRef: 'refs/pull/5/head',
          remoteUrl: 'https://github.com/emdash/emdash',
        },
      }),
      checkoutBranch: 'feature',
      lookups,
    });

    expect(lookups.byUrl).toHaveBeenCalledTimes(1);
  });

  it('degrades to branch matching only on old hosts with no observation', async () => {
    const pr = pullRequestFixture({ headRefName: 'feature' });
    const lookups = cacheOf([pr]);

    const prs = await derivePrAssociation({
      observed: null,
      checkoutBranch: 'feature',
      lookups,
    });

    expect(prs).toEqual([pr]);
    expect(lookups.byUrl).not.toHaveBeenCalled();
  });

  it('uses the observed branch for fallback when the checkout store has none yet', async () => {
    const pr = pullRequestFixture({ headRefName: 'observed-branch' });
    const lookups = cacheOf([pr]);

    const prs = await derivePrAssociation({
      observed: observedFixture({ branch: 'observed-branch' }),
      checkoutBranch: null,
      lookups,
    });

    expect(prs).toEqual([pr]);
  });

  it('returns no association when no branch is known anywhere', async () => {
    const lookups = cacheOf([pullRequestFixture()]);

    const prs = await derivePrAssociation({
      observed: null,
      checkoutBranch: null,
      lookups,
    });

    expect(prs).toEqual([]);
    expect(lookups.byBranch).not.toHaveBeenCalled();
  });
});
