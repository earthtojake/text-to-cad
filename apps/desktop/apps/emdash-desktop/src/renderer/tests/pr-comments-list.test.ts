import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { CommentsList } from '@core/features/source-control/browser/diff-view/changes-panel/components/pr-entry/comments-list';
import { buildPullRequestConversationItems } from '@core/features/source-control/browser/diff-view/changes-panel/components/pr-entry/pull-request-conversation';
import type { PullRequest, PullRequestComment } from '@core/services/pull-requests/api';

vi.mock('@core/primitives/theme/browser', () => ({
  useTheme: () => ({ effectiveTheme: 'emlight' }),
}));

vi.mock('@core/features/tasks/api/browser/task-state/task-selectors', () => ({
  getTaskView: vi.fn(),
}));

vi.mock('@core/primitives/navigation/browser/navigation-selectors', () => ({
  getNavigation: () => ({
    currentViewId: 'home',
    currentRef: { viewId: 'home', params: {}, key: 'home' },
  }),
}));

vi.mock('@core/primitives/desktop-host/browser/host-client', () => ({
  openExternal: vi.fn(),
}));

function makeComment(
  body: string,
  overrides: Partial<PullRequestComment> = {}
): PullRequestComment {
  return {
    id: 'issue-comment:1',
    pullRequestUrl: 'https://github.com/org/repo/pull/1',
    kind: 'issue',
    body,
    url: 'https://github.com/org/repo/pull/1#issuecomment-1',
    author: {
      userId: '1',
      userName: 'arnestrickmann',
      displayName: 'Arne Strickmann',
      avatarUrl: null,
      url: 'https://github.com/arnestrickmann',
      userUpdatedAt: null,
      userCreatedAt: null,
    },
    path: null,
    line: null,
    isResolved: false,
    isOutdated: false,
    createdAt: '2026-05-16T00:00:00Z',
    updatedAt: '2026-05-16T00:00:00Z',
    ...overrides,
  };
}

function makePullRequest(overrides: Partial<PullRequest> = {}): PullRequest {
  return {
    url: 'https://github.com/org/repo/pull/1',
    provider: 'github',
    repositoryUrl: 'https://github.com/org/repo',
    baseRefName: 'main',
    baseRefOid: 'base',
    headRepositoryUrl: 'https://github.com/org/repo',
    headRefName: 'feature',
    headRefOid: 'head',
    identifier: '#1',
    title: 'Add feature',
    description: 'PR body',
    status: 'open',
    isDraft: false,
    additions: 1,
    deletions: 0,
    changedFiles: 1,
    commitCount: 1,
    mergeableStatus: 'MERGEABLE',
    mergeStateStatus: 'CLEAN',
    reviewDecision: null,
    createdAt: '2026-05-10T00:00:00Z',
    updatedAt: '2026-05-12T00:00:00Z',
    author: {
      userId: '1',
      userName: 'arnestrickmann',
      displayName: 'Arne Strickmann',
      avatarUrl: null,
      url: 'https://github.com/arnestrickmann',
      userUpdatedAt: null,
      userCreatedAt: null,
    },
    labels: [],
    assignees: [],
    checks: [],
    ...overrides,
  };
}

describe('CommentsList', () => {
  it('renders HTML image comments from non-bot authors', () => {
    const html = renderToStaticMarkup(
      React.createElement(CommentsList, {
        comments: [
          makeComment('<img width="944" alt="Image" src="https://github.com/user/image.png">'),
        ],
      })
    );

    expect(html).toContain('src="https://github.com/user/image.png"');
    expect(html).toContain('alt="Image"');
    expect(html).toContain('aria-label="Expand image"');
    expect(html).toContain('width="944"');
  });

  it('renders comments by creation time rather than update time', () => {
    const html = renderToStaticMarkup(
      React.createElement(CommentsList, {
        comments: [
          makeComment('Second comment edited later', {
            id: 'issue-comment:2',
            createdAt: '2026-05-12T00:00:00Z',
            updatedAt: '2026-05-20T00:00:00Z',
          }),
          makeComment('First comment', {
            id: 'issue-comment:1',
            createdAt: '2026-05-11T00:00:00Z',
            updatedAt: '2026-05-11T00:00:00Z',
          }),
        ],
      })
    );

    expect(html.indexOf('First comment')).toBeLessThan(html.indexOf('Second comment edited later'));
  });

  it('keeps the error state visible when conversation items are present', () => {
    const html = renderToStaticMarkup(
      React.createElement(CommentsList, {
        comments: [makeComment('PR body')],
        error: new Error('failed'),
      })
    );

    expect(html).toContain('PR body');
    expect(html).toContain('Unable to load comments');
  });
});

describe('buildPullRequestConversationItems', () => {
  it('prepends the pull request description before comments', () => {
    const items = buildPullRequestConversationItems(makePullRequest(), [
      makeComment('Earlier external comment', {
        createdAt: '2026-05-09T00:00:00Z',
        updatedAt: '2026-05-09T00:00:00Z',
      }),
    ]);

    expect(items.map((item) => item.kind)).toEqual(['description', 'issue']);
    expect(items[0]?.body).toBe('PR body');
  });
});
