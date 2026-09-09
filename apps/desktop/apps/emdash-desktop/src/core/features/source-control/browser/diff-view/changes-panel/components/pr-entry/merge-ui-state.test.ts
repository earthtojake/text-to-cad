import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  MergeStateStatus,
  PullRequest,
  PullRequestCheck,
} from '@core/services/pull-requests/api';
import { MergeFooter } from './merge-footer';
import { computeMergeUiState, deriveMergeCheckState, type MergeUiState } from './merge-ui-state';

function makePr(overrides: Partial<PullRequest> = {}): PullRequest {
  return {
    url: 'https://github.com/acme/repo/pull/1',
    provider: 'github',
    repositoryUrl: 'https://github.com/acme/repo',
    baseRefName: 'main',
    baseRefOid: 'base',
    headRepositoryUrl: 'https://github.com/acme/repo',
    headRefName: 'feature',
    headRefOid: 'head',
    identifier: '#1',
    title: 'Test PR',
    description: null,
    status: 'open',
    isDraft: false,
    additions: null,
    deletions: null,
    changedFiles: null,
    commitCount: null,
    mergeableStatus: 'MERGEABLE',
    mergeStateStatus: 'CLEAN',
    reviewDecision: null,
    createdAt: '2026-05-30T00:00:00.000Z',
    updatedAt: '2026-05-30T00:00:00.000Z',
    author: null,
    labels: [],
    assignees: [],
    checks: [],
    ...overrides,
  };
}

function makeCheck(overrides: Partial<PullRequestCheck> = {}): PullRequestCheck {
  return {
    id: 'check-1',
    pullRequestUrl: 'https://github.com/acme/repo/pull/1',
    commitSha: 'head',
    name: 'CI',
    status: 'IN_PROGRESS',
    conclusion: 'NEUTRAL',
    detailsUrl: null,
    startedAt: null,
    completedAt: null,
    workflowName: null,
    appName: null,
    appLogoUrl: null,
    ...overrides,
  };
}

describe('deriveMergeCheckState', () => {
  it('classifies pending checks before a merge UI state is resolved', () => {
    expect(deriveMergeCheckState([makeCheck()])).toBe('pending');
  });

  it('classifies failed checks before a merge UI state is resolved', () => {
    expect(deriveMergeCheckState([makeCheck({ status: 'COMPLETED', conclusion: 'FAILURE' })])).toBe(
      'failed'
    );
  });

  it('classifies successful checks as passing', () => {
    expect(deriveMergeCheckState([makeCheck({ status: 'COMPLETED', conclusion: 'SUCCESS' })])).toBe(
      'passing'
    );
  });

  it('classifies skipped or cancelled checks without passing checks as unknown', () => {
    expect(
      deriveMergeCheckState([
        makeCheck({ status: 'COMPLETED', conclusion: 'SKIPPED' }),
        makeCheck({ id: 'check-2', status: 'COMPLETED', conclusion: 'CANCELLED' }),
      ])
    ).toBe('unknown');
  });

  it('classifies missing checks as unknown', () => {
    expect(deriveMergeCheckState([])).toBe('unknown');
  });
});

describe('computeMergeUiState', () => {
  it.each(['BLOCKED', 'BEHIND', 'HAS_HOOKS', 'UNSTABLE'] satisfies MergeStateStatus[])(
    'allows bypassing requirements when merge state is %s',
    (mergeStateStatus) => {
      expect(computeMergeUiState(makePr({ mergeStateStatus }))).toMatchObject({
        canMerge: false,
        canBypassRequirements: true,
      });
    }
  );

  it('keeps clean pull requests on the normal merge path', () => {
    expect(computeMergeUiState(makePr({ mergeStateStatus: 'CLEAN' }))).toMatchObject({
      canMerge: true,
      canBypassRequirements: false,
    });
  });

  it.each(['DIRTY', 'UNKNOWN'] satisfies MergeStateStatus[])(
    'does not offer bypass for non-requirement merge state %s',
    (mergeStateStatus) => {
      expect(computeMergeUiState(makePr({ mergeStateStatus }))).toMatchObject({
        canMerge: false,
        canBypassRequirements: false,
      });
    }
  );

  it('does not offer bypass for draft pull requests', () => {
    expect(
      computeMergeUiState(makePr({ isDraft: true, mergeStateStatus: 'BLOCKED' }))
    ).toMatchObject({
      kind: 'draft',
      canMerge: false,
      canBypassRequirements: false,
    });
  });

  it('shows checks as still running when an unstable pull request only has pending checks', () => {
    expect(
      computeMergeUiState(
        makePr({
          mergeStateStatus: 'UNSTABLE',
          checks: [makeCheck(), makeCheck({ id: 'check-2', status: 'QUEUED' })],
        })
      )
    ).toMatchObject({
      kind: 'unstable',
      title: 'Checks still running',
      detail: 'Waiting for GitHub checks to finish.',
      canMerge: false,
      canBypassRequirements: true,
    });
  });

  it('shows checks as not passing when an unstable pull request has failed checks', () => {
    expect(
      computeMergeUiState(
        makePr({
          mergeStateStatus: 'UNSTABLE',
          checks: [makeCheck({ status: 'COMPLETED', conclusion: 'FAILURE' })],
        })
      )
    ).toMatchObject({
      kind: 'unstable',
      title: 'Checks not passing',
      detail: 'Review failing checks before merging.',
      canMerge: false,
      canBypassRequirements: true,
    });
  });

  it('shows passing checks separately when an unstable pull request has no failing checks', () => {
    expect(
      computeMergeUiState(
        makePr({
          mergeStateStatus: 'UNSTABLE',
          checks: [makeCheck({ status: 'COMPLETED', conclusion: 'SUCCESS' })],
        })
      )
    ).toMatchObject({
      kind: 'unstable',
      title: 'Checks passing, but PR is unstable',
      detail: 'GitHub still reports the branch as unstable. Review branch rules before merging.',
      canMerge: false,
      canBypassRequirements: true,
    });
  });
});

describe('MergeFooter', () => {
  let dom: JSDOM;
  let root: Root;
  let container: HTMLDivElement;

  beforeEach(() => {
    dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>');
    vi.stubGlobal('window', dom.window);
    vi.stubGlobal('document', dom.window.document);
    vi.stubGlobal('HTMLElement', dom.window.HTMLElement);
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);

    container = dom.window.document.getElementById('root') as HTMLDivElement;
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    vi.unstubAllGlobals();
    dom.window.close();
  });

  function renderFooter(uiState: MergeUiState, bypassRequirements = false) {
    act(() => {
      root.render(
        React.createElement(MergeFooter, {
          uiState,
          mergeActions: [
            {
              value: 'merge',
              label: uiState.canBypassRequirements
                ? 'Bypass rules and merge'
                : 'Merge pull request',
              action: vi.fn(),
            },
          ],
          isMerging: false,
          isMarkingReady: false,
          bypassRequirements,
          onMarkReady: vi.fn(),
          onBypassRequirementsChange: vi.fn(),
        })
      );
    });
  }

  function getMergeButton() {
    return Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.toLowerCase().includes('merge')
    ) as HTMLButtonElement | undefined;
  }

  it('requires acknowledging bypass before enabling the merge action', () => {
    renderFooter(computeMergeUiState(makePr({ mergeStateStatus: 'BLOCKED' })));

    expect(getMergeButton()?.disabled).toBe(true);
    expect(container.textContent).toContain(
      'Merge without waiting for requirements to be met (bypass rules)'
    );
  });

  it('enables the merge action after bypass is acknowledged', () => {
    renderFooter(computeMergeUiState(makePr({ mergeStateStatus: 'BLOCKED' })), true);

    expect(getMergeButton()?.disabled).toBe(false);
    expect(getMergeButton()?.textContent).toContain('Bypass rules and merge');
    expect(container.textContent).not.toContain('Merging is blocked');
    expect(container.textContent).toContain('Bypass requirements enabled');
  });

  it('keeps the merge action disabled for conflicts', () => {
    renderFooter(computeMergeUiState(makePr({ mergeStateStatus: 'DIRTY' })));

    expect(getMergeButton()?.disabled).toBe(true);
  });
});
