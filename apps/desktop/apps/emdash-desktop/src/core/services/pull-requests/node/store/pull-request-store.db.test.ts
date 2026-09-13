import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { compileDrizzleSchemaToSql } from '@emdash/core/primitives/sqlite-store/codegen';
import { fingerprintDerivedSchema } from '@emdash/core/primitives/sqlite-store/node';
import { afterEach, describe, expect, it } from 'vitest';
import type { PullRequest, PullRequestComment } from '../../api';
import { PullRequestStore } from './pull-request-store';
import * as schema from './schema';
import { schemaFingerprint, schemaSqlStatements } from './schema-sql.generated';
import { pullRequestSqliteStore } from './store';

const cleanups: Array<() => Promise<void> | void> = [];

afterEach(async () => {
  while (cleanups.length > 0) await cleanups.pop()?.();
});

describe('pull request schema', () => {
  it('matches the checked-in in-memory Drizzle compilation', async () => {
    const statements = await compileDrizzleSchemaToSql(schema);
    expect(statements).toEqual([...schemaSqlStatements]);
    expect(fingerprintDerivedSchema(statements)).toBe(schemaFingerprint);
  });

  it('persists no account binding (identity is a per-sync runtime parameter)', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    cleanups.push(() => handle.close());
    const columnNames = (table: string) =>
      handle.connection
        .all<{ name: string }>(`PRAGMA table_info(${table})`)
        .map((column) => column.name);
    expect(columnNames('registered_repositories')).not.toContain('account_key');
    expect(columnNames('sync_cursors')).not.toContain('account_key');
  });

  it('rebuilds derived data when the fingerprint changes', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'emdash-pr-store-'));
    cleanups.push(async () => await rm(directory, { recursive: true, force: true }));
    const path = join(directory, 'pull-requests.db');
    const first = pullRequestSqliteStore.open(path);
    new PullRequestStore(first).registerRepository('https://github.com/emdash/emdash');
    first.connection.exec(`PRAGMA user_version = ${schemaFingerprint - 1}`);
    first.close();

    const reopened = pullRequestSqliteStore.open(path);
    cleanups.push(() => reopened.close());
    expect(
      reopened.connection.get<{ count: number }>(
        'SELECT COUNT(*) AS count FROM registered_repositories'
      )?.count
    ).toBe(0);
  });
});

describe('PullRequestStore', () => {
  it('lists, searches, filters, and paginates assembled pull requests', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    cleanups.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    store.savePullRequest(pullRequestFixture({ url: `${repositoryUrl}/pull/1`, title: 'Alpha' }));
    store.savePullRequest(
      pullRequestFixture({
        url: `${repositoryUrl}/pull/2`,
        identifier: '#2',
        title: 'Beta feature',
        labels: [{ name: 'feature', color: '00ff00' }],
      })
    );

    const first = store.listPullRequests({
      repositoryUrls: [repositoryUrl],
      cursor: null,
      limit: 1,
      sort: 'oldest',
    });
    expect(first.prs).toHaveLength(1);
    expect(first.nextCursor).not.toBeNull();
    const second = store.listPullRequests({
      repositoryUrls: [repositoryUrl],
      cursor: first.nextCursor,
      limit: 1,
    });
    expect(second.prs).toHaveLength(1);
    const filtered = store.listPullRequests({
      repositoryUrls: [repositoryUrl],
      cursor: null,
      limit: 10,
      searchQuery: 'Beta',
      filters: { labelNames: ['feature'] },
    });
    expect(filtered.prs.map((pr) => pr.title)).toEqual(['Beta feature']);
    expect(filtered.prs[0]?.author?.userName).toBe('octocat');
    expect(store.getFilterOptions([repositoryUrl]).labels).toEqual([
      { name: 'feature', color: '00ff00' },
    ]);
  });

  it('cascades sync cursors when a repository is unregistered', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    cleanups.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    store.setCursor(repositoryUrl, 'full', {
      lastUpdatedAt: new Date(0).toISOString(),
      done: true,
    });
    store.unregisterRepository(repositoryUrl);
    expect(
      handle.connection.get<{ count: number }>('SELECT COUNT(*) AS count FROM sync_cursors')?.count
    ).toBe(0);
  });

  it('keeps fork pull requests reachable from another registered repository', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    cleanups.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const baseRepositoryUrl = 'https://github.com/emdash/emdash';
    const headRepositoryUrl = 'https://github.com/contributor/emdash';
    store.registerRepository(baseRepositoryUrl);
    store.registerRepository(headRepositoryUrl);
    store.savePullRequest(
      pullRequestFixture({
        repositoryUrl: baseRepositoryUrl,
        headRepositoryUrl,
      })
    );

    store.unregisterRepository(baseRepositoryUrl);
    expect(
      handle.connection.get<{ count: number }>('SELECT COUNT(*) AS count FROM pull_requests')?.count
    ).toBe(1);
    expect(
      handle.connection.get<{ count: number }>('SELECT COUNT(*) AS count FROM pull_request_users')
        ?.count
    ).toBe(1);

    store.unregisterRepository(headRepositoryUrl);
    expect(
      handle.connection.get<{ count: number }>('SELECT COUNT(*) AS count FROM pull_requests')?.count
    ).toBe(0);
    expect(
      handle.connection.get<{ count: number }>('SELECT COUNT(*) AS count FROM pull_request_users')
        ?.count
    ).toBe(0);
  });

  it('prunes orphan users when old pull requests are archived', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    cleanups.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    store.savePullRequest(
      pullRequestFixture({
        status: 'closed',
        updatedAt: '2020-01-01T00:00:00.000Z',
      })
    );

    store.archiveOldPullRequests(repositoryUrl, '2021-01-01T00:00:00.000Z');

    expect(
      handle.connection.get<{ count: number }>('SELECT COUNT(*) AS count FROM pull_request_users')
        ?.count
    ).toBe(0);
  });

  it('persists and replaces comments and their ETag state', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    cleanups.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const pullRequest = pullRequestFixture();
    store.registerRepository(pullRequest.repositoryUrl);
    store.savePullRequest(pullRequest);

    store.replaceComments(pullRequest.url, [
      pullRequestCommentFixture({ id: 'issue-comment:1', pullRequestUrl: pullRequest.url }),
      pullRequestCommentFixture({
        id: 'review-comment:2',
        pullRequestUrl: pullRequest.url,
        body: 'Inline feedback',
        path: 'src/index.ts',
        line: 42,
        isOutdated: true,
      }),
    ]);
    store.setCommentState(pullRequest.url, '"etag-1"');

    expect(store.getComments(pullRequest.url)).toMatchObject([
      { id: 'issue-comment:1', author: { userId: 'commenter' } },
      {
        id: 'review-comment:2',
        body: 'Inline feedback',
        path: 'src/index.ts',
        line: 42,
        isOutdated: true,
      },
    ]);
    expect(store.getCommentState(pullRequest.url)).toMatchObject({ etag: '"etag-1"' });

    store.replaceComments(pullRequest.url, [
      pullRequestCommentFixture({
        id: 'review:3',
        pullRequestUrl: pullRequest.url,
        body: 'Replacement',
      }),
    ]);
    store.setCommentState(pullRequest.url, '"etag-2"');

    expect(store.getComments(pullRequest.url).map((comment) => comment.id)).toEqual(['review:3']);
    expect(store.getCommentState(pullRequest.url)).toMatchObject({ etag: '"etag-2"' });
  });

  it('cascades comment data and preserves referenced comment authors during pruning', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    cleanups.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    const cachedPullRequest = pullRequestFixture({
      url: `${repositoryUrl}/pull/1`,
      author: null,
    });
    store.registerRepository(repositoryUrl);
    store.savePullRequest(cachedPullRequest);
    store.replaceComments(cachedPullRequest.url, [
      pullRequestCommentFixture({ pullRequestUrl: cachedPullRequest.url }),
    ]);
    store.setCommentState(cachedPullRequest.url, '"etag"');
    store.savePullRequest(
      pullRequestFixture({
        url: `${repositoryUrl}/pull/2`,
        status: 'closed',
        updatedAt: '2020-01-01T00:00:00.000Z',
      })
    );

    store.archiveOldPullRequests(repositoryUrl, '2021-01-01T00:00:00.000Z');

    expect(store.getComments(cachedPullRequest.url)).toHaveLength(1);
    expect(
      handle.connection.get<{ count: number }>(
        "SELECT COUNT(*) AS count FROM pull_request_users WHERE user_id = 'commenter'"
      )?.count
    ).toBe(1);

    store.savePullRequest({
      ...cachedPullRequest,
      status: 'closed',
      updatedAt: '2020-01-01T00:00:00.000Z',
    });
    store.archiveOldPullRequests(repositoryUrl, '2021-01-01T00:00:00.000Z');

    expect(store.getComments(cachedPullRequest.url)).toEqual([]);
    expect(store.getCommentState(cachedPullRequest.url)).toBeNull();
    expect(
      handle.connection.get<{ count: number }>(
        "SELECT COUNT(*) AS count FROM pull_request_users WHERE user_id = 'commenter'"
      )?.count
    ).toBe(0);
  });
});

function pullRequestFixture(overrides: Partial<PullRequest> = {}): PullRequest {
  const repositoryUrl = 'https://github.com/emdash/emdash';
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
    author: {
      userId: '1',
      userName: 'octocat',
      displayName: 'Octocat',
      avatarUrl: null,
      url: null,
      userUpdatedAt: null,
      userCreatedAt: null,
    },
    labels: [],
    assignees: [],
    checks: [],
    ...overrides,
  };
}

function pullRequestCommentFixture(
  overrides: Partial<PullRequestComment> = {}
): PullRequestComment {
  return {
    id: 'issue-comment:1',
    pullRequestUrl: 'https://github.com/emdash/emdash/pull/1',
    kind: 'issue',
    body: 'Looks good',
    url: 'https://github.com/emdash/emdash/pull/1#issuecomment-1',
    author: {
      userId: 'commenter',
      userName: 'reviewer',
      displayName: 'Reviewer',
      avatarUrl: null,
      url: null,
      userUpdatedAt: null,
      userCreatedAt: null,
    },
    path: null,
    line: null,
    isResolved: false,
    isOutdated: false,
    createdAt: '2026-01-03T00:00:00.000Z',
    updatedAt: '2026-01-03T00:00:00.000Z',
    ...overrides,
  };
}
