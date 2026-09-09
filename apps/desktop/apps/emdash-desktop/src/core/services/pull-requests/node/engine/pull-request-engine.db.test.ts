import { err, ok } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import {
  requestPriorities,
  type CreateRequestSchedulerOptions,
  type RateGate,
  type RequestScheduler,
  type ScheduledRequest,
} from '@emdash/shared/requests';
import { retrySchedules } from '@emdash/shared/scheduling';
import { createStubLogger } from '@emdash/shared/testing';
import type { ContractClient } from '@emdash/wire/rpc';
import type { Octokit } from '@octokit/rest';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { GitHubAuthContract, PullRequest, PullRequestComment, SyncState } from '../../api';
import { PullRequestStore, pullRequestSqliteStore } from '../store';
import { PullRequestEngine, type PullRequestEngineOptions } from './pull-request-engine';

const closeHandles: Array<() => void> = [];
const scopes: Scope[] = [];

afterEach(async () => {
  await Promise.all(scopes.splice(0).map(async (scope) => await scope.dispose()));
  while (closeHandles.length > 0) closeHandles.pop()?.();
});

describe('PullRequestEngine', () => {
  it('syncs GitHub pull requests into the private store and emits state', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    const states: SyncState[] = [];
    const graphql = vi.fn(async () => ({
      repository: {
        pullRequests: {
          totalCount: 1,
          pageInfo: { hasNextPage: false, endCursor: null },
          nodes: [gqlPullRequest()],
        },
      },
    }));
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () => fakeOctokit(graphql),
      onSyncState: (_repositoryUrl, state) => states.push(state),
    });

    const result = await engine.sync(repositoryUrl, new AbortController().signal);
    expect(result).toEqual(ok());
    expect(
      store.listPullRequests({ repositoryUrls: [repositoryUrl], cursor: null, limit: 10 }).prs
    ).toMatchObject([
      {
        title: 'Worker-owned PR',
        identifier: '#42',
        author: { userId: 'github.com:1' },
      },
    ]);
    expect(store.getCursor(repositoryUrl, 'full')?.done).toBe(true);
    expect(store.getCursor(repositoryUrl, 'full')?.lastUpdatedAt).toBe('2026-01-02T00:00:00.000Z');
    expect(states.at(-1)).toMatchObject({ phase: 'idle', kind: 'full', synced: 1 });
  });

  it('skips the sync with a surfaced error status when identity is unresolvable', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    const graphql = vi.fn();
    const states: SyncState[] = [];
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: {
        resolveAuth: async () =>
          err({
            type: 'account_unresolvable',
            host: 'github.com',
            message: 'The pinned GitHub account no longer exists.',
          }),
      },
      logger,
      createOctokit: () => fakeOctokit(graphql),
      onSyncState: (_repositoryUrl, state) => states.push(state),
    });

    const result = await engine.sync(repositoryUrl, new AbortController().signal);

    expect(result).toEqual(
      err({
        type: 'github_account_not_found',
        message: 'The pinned GitHub account no longer exists.',
      })
    );
    expect(graphql).not.toHaveBeenCalled();
    expect(store.getCursor(repositoryUrl, 'full')).toBeNull();
    expect(states.at(-1)).toMatchObject({
      phase: 'error',
      kind: 'full',
      error: { type: 'github_account_not_found' },
    });
  });

  it('surfaces an explicitly disabled GitHub account instead of syncing', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: {
        resolveAuth: async () =>
          err({
            type: 'github_disabled',
            host: 'github.com',
            message: 'GitHub is disabled for this project.',
          }),
      },
      logger,
      createOctokit: () => fakeOctokit(vi.fn()),
    });

    await expect(engine.sync(repositoryUrl, new AbortController().signal)).resolves.toEqual(
      err({
        type: 'sync_failed',
        message: 'GitHub is disabled for this project.',
      })
    );
  });

  it('invalidates sync cursors when the resolved identity changes', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    store.setCursor(repositoryUrl, 'full', {
      lastUpdatedAt: '2026-01-01T00:00:00.000Z',
      done: true,
    });
    let accountId = 'account-1';
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: {
        resolveAuth: async () =>
          ok({
            token: 'test-token',
            host: 'github.com',
            apiBaseUrl: 'https://api.github.com',
            accountId,
          }),
      },
      logger,
      createOctokit: () =>
        fakeOctokit(vi.fn(async () => ({ repository: { pullRequest: gqlPullRequest() } }))),
    });

    await engine.syncSingle(repositoryUrl, 42, new AbortController().signal);
    expect(store.getCursor(repositoryUrl, 'full')?.done).toBe(true);

    accountId = 'account-2';
    await engine.syncSingle(repositoryUrl, 42, new AbortController().signal);
    expect(store.getCursor(repositoryUrl, 'full')).toBeNull();
  });

  it('aborts an in-flight request without advancing its cursor', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    let started = false;
    const graphql = vi.fn(
      async (_query: string, variables: { request: { signal: AbortSignal } }) =>
        await new Promise<never>((_resolve, reject) => {
          started = true;
          variables.request.signal.addEventListener(
            'abort',
            () => reject(new DOMException('Aborted', 'AbortError')),
            { once: true }
          );
        })
    );
    const { logger } = createStubLogger();
    const states: SyncState[] = [];
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () => fakeOctokit(graphql),
      onSyncState: (_repositoryUrl, state) => states.push(state),
    });
    const controller = new AbortController();

    const sync = engine.sync(repositoryUrl, controller.signal);
    await vi.waitFor(() => expect(started).toBe(true));
    controller.abort(new Error('Scope disposed'));
    const result = await sync;
    expect(result.success).toBe(false);
    expect(store.getCursor(repositoryUrl, 'full')).toBeNull();
    expect(states.at(-1)).toMatchObject({ phase: 'idle', kind: 'full' });
  });

  it('resumes incremental sync without skipping older pages', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    store.setCursor(repositoryUrl, 'full', {
      lastUpdatedAt: '2026-01-01T00:00:00.000Z',
      done: true,
    });
    const firstAttempt = vi
      .fn()
      .mockResolvedValueOnce({
        repository: {
          pullRequests: {
            pageInfo: { hasNextPage: true, endCursor: 'page-2' },
            nodes: [
              gqlPullRequest({
                number: 43,
                title: 'Newest page',
                updatedAt: '2026-01-03T00:00:00.000Z',
              }),
            ],
          },
        },
      })
      .mockRejectedValueOnce(Object.assign(new Error('Worker stopped'), { status: 400 }));
    const { logger } = createStubLogger();
    const interruptedEngine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () => fakeOctokit(firstAttempt),
    });

    expect(
      (await interruptedEngine.sync(repositoryUrl, new AbortController().signal)).success
    ).toBe(false);
    expect(store.getCursor(repositoryUrl, 'incremental')).toEqual({
      lastUpdatedAt: '2026-01-01T00:00:00.000Z',
      pageCursor: 'page-2',
      done: false,
    });

    const resumedGraphql = vi.fn(async () => ({
      repository: {
        pullRequests: {
          pageInfo: { hasNextPage: false, endCursor: null },
          nodes: [
            gqlPullRequest({
              number: 44,
              title: 'Older page',
              updatedAt: '2026-01-02T00:00:00.000Z',
            }),
          ],
        },
      },
    }));
    const resumedEngine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () => fakeOctokit(resumedGraphql),
    });

    expect(await resumedEngine.sync(repositoryUrl, new AbortController().signal)).toEqual(ok());
    expect(resumedGraphql).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ cursor: 'page-2' })
    );
    expect(
      store.listPullRequests({ repositoryUrls: [repositoryUrl], cursor: null, limit: 10 }).prs
    ).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ identifier: '#43' }),
        expect.objectContaining({ identifier: '#44' }),
      ])
    );
    expect(store.getCursor(repositoryUrl, 'incremental')).toEqual({
      lastUpdatedAt: '2026-01-03T00:00:00.000Z',
      pageCursor: undefined,
      done: true,
    });
  });

  it('emits a terminal error state when a single pull request is not found', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    store.registerRepository('https://github.com/emdash/emdash');
    const states: SyncState[] = [];
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () =>
        fakeOctokit(
          vi.fn(async () => ({
            repository: { pullRequest: null },
          }))
        ),
      onSyncState: (_repositoryUrl, state) => states.push(state),
    });

    const result = await engine.syncSingle(
      'https://github.com/emdash/emdash',
      404,
      new AbortController().signal
    );

    expect(result.success).toBe(false);
    expect(states.at(-1)).toMatchObject({
      phase: 'error',
      kind: 'single',
      error: {
        type: 'github_not_found_or_no_access',
        host: 'github.com',
        message: 'Pull request #404 was not found',
      },
    });

    const stateCount = states.length;
    const quietResult = await engine.syncSingle(
      'https://github.com/emdash/emdash',
      404,
      new AbortController().signal,
      { emit: false }
    );
    expect(quietResult.success).toBe(false);
    expect(states).toHaveLength(stateCount);
  });

  it('emits only completion when a quiet single refresh succeeds', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    const states: SyncState[] = [];
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () =>
        fakeOctokit(
          vi.fn(async () => ({
            repository: { pullRequest: gqlPullRequest() },
          }))
        ),
      onSyncState: (_repositoryUrl, state) => states.push(state),
    });

    await expect(
      engine.syncSingle(repositoryUrl, 42, new AbortController().signal, { emit: false })
    ).resolves.toMatchObject({ success: true });
    expect(states).toHaveLength(1);
    expect(states[0]).toMatchObject({
      phase: 'idle',
      kind: 'single',
      synced: 1,
      lastSyncedAt: expect.any(Number),
    });
  });

  it('falls back to a full sync after incremental overflow', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    store.setCursor(repositoryUrl, 'full', {
      lastUpdatedAt: '2026-01-01T00:00:00.000Z',
      done: true,
    });
    const graphql = vi
      .fn()
      .mockResolvedValueOnce({
        repository: {
          pullRequests: {
            pageInfo: { hasNextPage: true, endCursor: 'page-2' },
            nodes: [gqlPullRequest({ updatedAt: '2026-01-03T00:00:00.000Z' })],
          },
        },
      })
      .mockResolvedValueOnce({
        repository: {
          pullRequests: {
            totalCount: 0,
            pageInfo: { hasNextPage: false, endCursor: null },
            nodes: [],
          },
        },
      });
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      maxSyncCount: 1,
      createOctokit: () => fakeOctokit(graphql),
    });

    await expect(engine.sync(repositoryUrl, new AbortController().signal)).resolves.toEqual(ok());
    expect(store.getCursor(repositoryUrl, 'full')).toBeNull();
    await expect(engine.sync(repositoryUrl, new AbortController().signal)).resolves.toEqual(ok());
    expect(graphql).toHaveBeenCalledTimes(2);
    expect(store.getCursor(repositoryUrl, 'full')?.done).toBe(true);
  });

  it('host-qualifies REST comment author IDs', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    const listComments = vi.fn();
    const listReviewComments = vi.fn();
    const listReviews = vi.fn();
    const paginate = vi.fn(async (method: unknown) =>
      method === listComments
        ? [
            {
              id: 7,
              body: 'Comment',
              html_url: `${repositoryUrl}/pull/42#issuecomment-7`,
              created_at: '2026-01-01T00:00:00.000Z',
              updated_at: '2026-01-01T00:00:00.000Z',
              user: {
                id: 1,
                login: 'octocat',
                avatar_url: 'https://github.com/images/octocat.png',
                html_url: 'https://github.com/octocat',
              },
            },
          ]
        : []
    );
    const octokit = {
      graphql: vi.fn(),
      paginate,
      rest: {
        issues: { listComments },
        pulls: {
          get: vi.fn(async () => ({ headers: { etag: '"etag"' }, data: {} })),
          listReviewComments,
          listReviews,
        },
      },
    } as unknown as Octokit;
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () => octokit,
    });

    const result = await engine.getPullRequestComments(
      repositoryUrl,
      42,
      new AbortController().signal
    );

    expect(result).toMatchObject({
      success: true,
      data: [{ author: { userId: 'github.com:1' } }],
    });
  });

  it('persists comments and the pull request ETag on first fetch', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    const pullRequest = pullRequestFixture();
    store.registerRepository(repositoryUrl);
    store.savePullRequest(pullRequest);
    const github = fakeCommentsOctokit({
      etag: '"etag-1"',
      issueComments: [restIssueComment({ body: 'First comment' })],
    });
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () => github.octokit,
    });

    const result = await engine.getPullRequestComments(
      repositoryUrl,
      42,
      new AbortController().signal
    );

    expect(result).toMatchObject({
      success: true,
      data: [{ id: 'issue-comment:7', body: 'First comment' }],
    });
    expect(store.getComments(pullRequest.url)).toMatchObject([
      { id: 'issue-comment:7', body: 'First comment' },
    ]);
    expect(store.getCommentState(pullRequest.url)).toMatchObject({ etag: '"etag-1"' });
  });

  it('serves cached comments when the ETag guard returns 304', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    const pullRequest = pullRequestFixture();
    store.registerRepository(repositoryUrl);
    store.savePullRequest(pullRequest);
    store.replaceComments(pullRequest.url, [
      pullRequestCommentFixture({ pullRequestUrl: pullRequest.url, body: 'Cached comment' }),
    ]);
    store.setCommentState(pullRequest.url, '"etag-1"');
    const github = fakeCommentsOctokit({
      getError: Object.assign(new Error('Not modified'), { status: 304 }),
    });
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () => github.octokit,
    });

    const result = await engine.getPullRequestComments(
      repositoryUrl,
      42,
      new AbortController().signal
    );

    expect(result).toMatchObject({
      success: true,
      data: [{ body: 'Cached comment' }],
    });
    expect(github.get).toHaveBeenCalledWith(
      expect.objectContaining({ headers: { 'if-none-match': '"etag-1"' } })
    );
    expect(github.paginate).not.toHaveBeenCalled();
  });

  it('replaces cached comments and the ETag when the guard returns 200', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    const pullRequest = pullRequestFixture();
    store.registerRepository(repositoryUrl);
    store.savePullRequest(pullRequest);
    store.replaceComments(pullRequest.url, [
      pullRequestCommentFixture({ pullRequestUrl: pullRequest.url, body: 'Old comment' }),
    ]);
    store.setCommentState(pullRequest.url, '"etag-1"');
    const github = fakeCommentsOctokit({
      etag: '"etag-2"',
      issueComments: [restIssueComment({ id: 8, body: 'Fresh comment' })],
    });
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () => github.octokit,
    });

    const result = await engine.getPullRequestComments(
      repositoryUrl,
      42,
      new AbortController().signal
    );

    expect(result).toMatchObject({
      success: true,
      data: [{ id: 'issue-comment:8', body: 'Fresh comment' }],
    });
    expect(store.getComments(pullRequest.url).map((comment) => comment.body)).toEqual([
      'Fresh comment',
    ]);
    expect(store.getCommentState(pullRequest.url)).toMatchObject({ etag: '"etag-2"' });
  });

  it('returns stale cached comments when conditional refresh fails', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    const pullRequest = pullRequestFixture();
    store.registerRepository(repositoryUrl);
    store.savePullRequest(pullRequest);
    store.replaceComments(pullRequest.url, [
      pullRequestCommentFixture({ pullRequestUrl: pullRequest.url, body: 'Stale comment' }),
    ]);
    store.setCommentState(pullRequest.url, '"etag-1"');
    const github = fakeCommentsOctokit({
      getError: Object.assign(new Error('Unavailable'), { status: 503 }),
    });
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () => github.octokit,
      retrySchedule: retrySchedules.fixed(0, 0),
    });

    const result = await engine.getPullRequestComments(
      repositoryUrl,
      42,
      new AbortController().signal
    );

    expect(result).toMatchObject({
      success: true,
      data: [{ body: 'Stale comment' }],
    });
    expect(github.paginate).not.toHaveBeenCalled();
  });

  it('keeps check IDs stable across refreshes', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    const pullRequestUrl = `${repositoryUrl}/pull/42`;
    store.registerRepository(repositoryUrl);
    store.savePullRequest(pullRequestFixture());
    const graphql = vi.fn(async () => ({
      repository: {
        pullRequest: {
          commits: {
            nodes: [
              {
                commit: {
                  statusCheckRollup: {
                    contexts: {
                      pageInfo: { hasNextPage: false, endCursor: null },
                      nodes: [
                        {
                          __typename: 'CheckRun',
                          name: 'CI',
                          status: 'COMPLETED',
                          conclusion: 'SUCCESS',
                          detailsUrl: 'https://github.com/checks/1',
                          startedAt: '2026-01-01T00:00:00.000Z',
                          completedAt: '2026-01-01T00:01:00.000Z',
                          checkSuite: null,
                        },
                      ],
                    },
                  },
                },
              },
            ],
          },
        },
      },
    }));
    const { logger } = createStubLogger();
    const states: SyncState[] = [];
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () => fakeOctokit(graphql),
      onSyncState: (_repositoryUrl, state) => states.push(state),
    });

    await engine.syncChecks(repositoryUrl, pullRequestUrl, 'head', new AbortController().signal);
    const firstId = store.listPullRequests({
      repositoryUrls: [repositoryUrl],
      cursor: null,
      limit: 10,
    }).prs[0]?.checks[0]?.id;
    await engine.syncChecks(repositoryUrl, pullRequestUrl, 'head', new AbortController().signal);
    const secondId = store.listPullRequests({
      repositoryUrls: [repositoryUrl],
      cursor: null,
      limit: 10,
    }).prs[0]?.checks[0]?.id;

    expect(firstId).toBe('head:0:CI');
    expect(secondId).toBe(firstId);
    expect(states.at(-1)).toMatchObject({
      phase: 'idle',
      kind: 'single',
      lastSyncedAt: expect.any(Number),
    });
  });

  it('schedules background sync pages with retry through one account lane', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    const graphql = vi
      .fn()
      .mockRejectedValueOnce(Object.assign(new Error('Unavailable'), { status: 503 }))
      .mockResolvedValueOnce({
        repository: {
          pullRequests: {
            totalCount: 0,
            pageInfo: { hasNextPage: false, endCursor: null },
            nodes: [],
          },
        },
      });
    const requests: ScheduledRequest<unknown>[] = [];
    const scheduler = immediateScheduler(requests);
    const createScheduler = vi.fn((_options: CreateRequestSchedulerOptions) => scheduler);
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth('account-1'),
      logger,
      createOctokit: () => fakeOctokit(graphql),
      createScheduler,
      retrySchedule: retrySchedules.fixed(0, 1),
    });

    await expect(
      engine.sync(repositoryUrl, new AbortController().signal, requestPriorities.background)
    ).resolves.toEqual(ok());

    expect(graphql).toHaveBeenCalledTimes(2);
    expect(createScheduler).toHaveBeenCalledTimes(1);
    expect(requests).toHaveLength(2);
    expect(requests.every((request) => request.priority === requestPriorities.background)).toBe(
      true
    );
  });

  it('feeds GraphQL and HTTP rate-limit observations into the lane gate', async () => {
    const handle = await pullRequestSqliteStore.openTemp();
    closeHandles.push(() => handle.close());
    const store = new PullRequestStore(handle);
    const repositoryUrl = 'https://github.com/emdash/emdash';
    store.registerRepository(repositoryUrl);
    const resetAt = '2026-01-03T00:00:00.000Z';
    const graphql = vi.fn(async () => ({
      repository: {
        pullRequests: {
          totalCount: 0,
          pageInfo: { hasNextPage: false, endCursor: null },
          nodes: [],
        },
      },
      rateLimit: { cost: 2, remaining: 98, resetAt },
    }));
    type HookOptions = {
      url?: string;
      request?: { signal?: AbortSignal };
    };
    let beforeHook: ((options: HookOptions) => Promise<void>) | undefined;
    let afterHook:
      | ((
          response: { headers: Record<string, string | number | undefined> },
          options: HookOptions
        ) => void)
      | undefined;
    let errorHook: ((error: unknown, options: HookOptions) => never) | undefined;
    const octokit = {
      graphql,
      rest: {},
      paginate: vi.fn(),
      hook: {
        before: vi.fn((_name: string, callback: (options: HookOptions) => Promise<void>) => {
          beforeHook = callback;
        }),
        after: vi.fn(
          (
            _name: string,
            callback: (
              response: { headers: Record<string, string | number | undefined> },
              options: HookOptions
            ) => void
          ) => {
            afterHook = callback;
          }
        ),
        error: vi.fn((_name: string, callback: (error: unknown, options: HookOptions) => never) => {
          errorHook = callback;
        }),
      },
    } as unknown as Octokit;
    const gates = {
      graphql: fakeRateGate(),
      rest: fakeRateGate(),
    };
    const { logger } = createStubLogger();
    const engine = createEngine({
      store,
      githubAuth: fakeGitHubAuth(),
      logger,
      createOctokit: () => octokit,
      createScheduler: () => immediateScheduler([]),
      createRateGate: (resource) => gates[resource],
    });

    await expect(engine.sync(repositoryUrl, new AbortController().signal)).resolves.toEqual(ok());
    expect(gates.graphql.observe).toHaveBeenCalledWith({
      cost: 2,
      remaining: 98,
      resetAtMs: Date.parse(resetAt),
    });
    expect(gates.rest.observe).not.toHaveBeenCalled();

    const requestSignal = new AbortController().signal;
    await beforeHook?.({
      url: 'https://api.github.com/graphql',
      request: { signal: requestSignal },
    });
    expect(gates.graphql.acquire).toHaveBeenLastCalledWith(0, requestSignal);
    await beforeHook?.({
      url: 'https://api.github.com/repos/emdash/emdash/pulls',
      request: { signal: requestSignal },
    });
    expect(gates.rest.acquire).toHaveBeenLastCalledWith(1, requestSignal);

    afterHook?.(
      {
        headers: {
          'x-ratelimit-resource': 'core',
          'x-ratelimit-remaining': '17',
          'x-ratelimit-reset': '100',
          'retry-after': '3',
        },
      },
      { url: 'https://api.github.com/graphql' }
    );
    expect(gates.rest.observe).toHaveBeenLastCalledWith({
      remaining: 17,
      resetAtMs: 100_000,
      retryAfterMs: 3_000,
    });

    const rateError = Object.assign(new Error('rate limited'), {
      response: { headers: { 'retry-after': '2' } },
    });
    expect(() =>
      errorHook?.(rateError, {
        url: 'https://api.github.com/repos/emdash/emdash/pulls',
      })
    ).toThrow(rateError);
    expect(gates.rest.observe).toHaveBeenLastCalledWith({
      remaining: undefined,
      resetAtMs: undefined,
      retryAfterMs: 2_000,
    });
  });
});

function createEngine(options: Omit<PullRequestEngineOptions, 'scope'>): PullRequestEngine {
  const scope = createScope({ label: 'pull-request-engine-test' });
  scopes.push(scope);
  return new PullRequestEngine({ ...options, scope });
}

function immediateScheduler(requests: ScheduledRequest<unknown>[]): RequestScheduler {
  return {
    stats: { pending: 0, inFlight: 0 },
    async submit<T>(
      request: ScheduledRequest<T>,
      options: { signal?: AbortSignal } = {}
    ): Promise<T> {
      requests.push(request as ScheduledRequest<unknown>);
      return await request.run(options.signal ?? new AbortController().signal);
    },
    async dispose(): Promise<void> {},
  };
}

function fakeRateGate(): RateGate {
  return {
    acquire: vi.fn(async () => {}),
    observe: vi.fn(),
  };
}

function fakeGitHubAuth(accountId?: string): ContractClient<GitHubAuthContract> {
  return {
    resolveAuth: async () =>
      ok({
        token: 'test-token',
        host: 'github.com',
        apiBaseUrl: 'https://api.github.com',
        accountId,
      }),
  };
}

function fakeOctokit(graphql: (...args: never[]) => Promise<unknown>): Octokit {
  return {
    graphql,
    rest: {},
    paginate: vi.fn(),
  } as unknown as Octokit;
}

function fakeCommentsOctokit(options: {
  etag?: string;
  getError?: unknown;
  issueComments?: Array<ReturnType<typeof restIssueComment>>;
}) {
  const get = options.getError
    ? vi.fn(async () => {
        throw options.getError;
      })
    : vi.fn(async () => ({ headers: { etag: options.etag ?? '"etag"' }, data: {} }));
  const listComments = vi.fn();
  const listReviewComments = vi.fn();
  const listReviews = vi.fn();
  const paginate = vi.fn(async (method: unknown) =>
    method === listComments ? (options.issueComments ?? []) : []
  );
  const octokit = {
    graphql: vi.fn(),
    paginate,
    rest: {
      issues: { listComments },
      pulls: { get, listReviewComments, listReviews },
    },
  } as unknown as Octokit;
  return { octokit, get, paginate };
}

function restIssueComment(overrides: { id?: number; body?: string } = {}) {
  return {
    id: overrides.id ?? 7,
    body: overrides.body ?? 'Comment',
    html_url: `https://github.com/emdash/emdash/pull/42#issuecomment-${overrides.id ?? 7}`,
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    user: {
      id: 1,
      login: 'octocat',
      avatar_url: 'https://github.com/images/octocat.png',
      html_url: 'https://github.com/octocat',
    },
  };
}

function gqlPullRequest(overrides: { number?: number; title?: string; updatedAt?: string } = {}) {
  return {
    number: overrides.number ?? 42,
    title: overrides.title ?? 'Worker-owned PR',
    url: `https://github.com/emdash/emdash/pull/${overrides.number ?? 42}`,
    state: 'OPEN',
    isDraft: false,
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: overrides.updatedAt ?? '2026-01-02T00:00:00.000Z',
    headRefName: 'feature',
    headRefOid: 'head',
    baseRefName: 'main',
    baseRefOid: 'base',
    commitCount: { totalCount: 1 },
    body: 'Description',
    additions: 10,
    deletions: 1,
    changedFiles: 2,
    mergeable: 'MERGEABLE',
    mergeStateStatus: 'CLEAN',
    author: {
      databaseId: 1,
      login: 'octocat',
      avatarUrl: '',
      url: 'https://github.com/octocat',
    },
    headRepository: { url: 'https://github.com/emdash/emdash' },
    baseRepository: { url: 'https://github.com/emdash/emdash' },
    labels: { nodes: [{ name: 'feature', color: '00ff00' }] },
    assignees: { nodes: [] },
    reviewDecision: null,
  };
}

function pullRequestFixture(): PullRequest {
  const repositoryUrl = 'https://github.com/emdash/emdash';
  return {
    url: `${repositoryUrl}/pull/42`,
    provider: 'github',
    repositoryUrl,
    baseRefName: 'main',
    baseRefOid: 'base',
    headRepositoryUrl: repositoryUrl,
    headRefName: 'feature',
    headRefOid: 'head',
    identifier: '#42',
    title: 'Feature',
    description: null,
    status: 'open',
    isDraft: false,
    additions: 1,
    deletions: 0,
    changedFiles: 1,
    commitCount: 1,
    mergeableStatus: 'MERGEABLE',
    mergeStateStatus: 'CLEAN',
    reviewDecision: null,
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z',
    author: null,
    labels: [],
    assignees: [],
    checks: [],
  };
}

function pullRequestCommentFixture(
  overrides: Partial<PullRequestComment> = {}
): PullRequestComment {
  const pullRequestUrl = 'https://github.com/emdash/emdash/pull/42';
  return {
    id: 'issue-comment:7',
    pullRequestUrl,
    kind: 'issue',
    body: 'Comment',
    url: `${pullRequestUrl}#issuecomment-7`,
    author: {
      userId: 'github.com:1',
      userName: 'octocat',
      displayName: 'octocat',
      avatarUrl: null,
      url: 'https://github.com/octocat',
      userUpdatedAt: null,
      userCreatedAt: null,
    },
    path: null,
    line: null,
    isResolved: false,
    isOutdated: false,
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z',
    ...overrides,
  };
}
