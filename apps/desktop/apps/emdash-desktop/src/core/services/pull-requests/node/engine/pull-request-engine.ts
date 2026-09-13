import { err, ok, type Result } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import type { Logger } from '@emdash/shared/logger';
import {
  createRequestScheduler,
  requestPriorities,
  createTokenBucketGate,
  type CreateRequestSchedulerOptions,
  type RateFeedback,
  type RateGate,
  type RequestScheduler,
} from '@emdash/shared/requests';
import { retry, retrySchedules, type RetrySchedule } from '@emdash/shared/scheduling';
import type { ContractClient } from '@emdash/wire/rpc';
import { Octokit } from '@octokit/rest';
import { parseRepositoryRef } from '@core/primitives/repository/api';
import type {
  GitHubAuthContract,
  PullRequest,
  PullRequestCheck,
  PullRequestComment,
  PullRequestError,
  PullRequestFile,
  PullRequestMergeOptions,
  PullRequestUser,
  SyncState,
} from '../../api';
import type { PullRequestStore, SyncCursor } from '../store';
import {
  isAbortError,
  isNetworkError,
  mapApiError,
  mapAuthError,
  type PullRequestOperationErrorType,
} from './errors';
import {
  GET_PR_BY_NUMBER_QUERY,
  GET_PR_CHECK_RUNS_BY_URL_QUERY,
  INCREMENTAL_SYNC_PRS_QUERY,
  SYNC_PRS_QUERY,
} from './queries';

const DEFAULT_MAX_SYNC_COUNT = 300;
const DEFAULT_ARCHIVE_AGE_MONTHS = 6;
const DEFAULT_REQUEST_CONCURRENCY = 3;
const DEFAULT_REQUEST_CAPACITY = 20;
const DEFAULT_REQUEST_REFILL_PER_SEC = 10;
const DEFAULT_REQUEST_RESERVE = 50;

const defaultRetrySchedule = retrySchedules.jitter(
  retrySchedules.exponential({
    initialMs: 1_000,
    maxMs: 30_000,
    maxRetries: 2,
  })
);

export type PullRequestEngineOptions = {
  store: PullRequestStore;
  githubAuth: ContractClient<GitHubAuthContract>;
  scope: Scope;
  logger: Logger;
  maxSyncCount?: number;
  archiveAgeMonths?: number;
  onSyncState?: (repositoryUrl: string, state: SyncState) => void;
  createOctokit?: (options: { token: string; baseUrl: string }) => Octokit;
  createScheduler?: (options: CreateRequestSchedulerOptions) => RequestScheduler;
  createRateGate?: (resource: GitHubRateResource) => RateGate;
  retrySchedule?: RetrySchedule;
};

type RequestLane = {
  scheduler: RequestScheduler;
  gates: Record<GitHubRateResource, RateGate>;
};

type GitHubRateResource = 'graphql' | 'rest';

type GitHubClient = {
  octokit: Octokit;
  lane: RequestLane;
};

type GraphQlRateLimit = {
  cost: number;
  remaining: number;
  resetAt: string;
};

type RequestOptions = {
  priority: number;
  cost?: number;
  key?: string;
};

type OctokitHeaders = Record<string, string | number | undefined>;

type OctokitRequestOptions = {
  url?: string;
  request?: { signal?: AbortSignal };
};

type OctokitRequestHook = {
  before?(name: 'request', callback: (options: OctokitRequestOptions) => Promise<void>): void;
  after(
    name: 'request',
    callback: (response: { headers: OctokitHeaders }, options: OctokitRequestOptions) => void
  ): void;
  error(name: 'request', callback: (error: unknown, options: OctokitRequestOptions) => never): void;
};

type RepositoryRef = NonNullable<ReturnType<typeof parseRepositoryRef>>;

interface GqlUser {
  databaseId?: number;
  login: string;
  avatarUrl: string;
  createdAt?: string;
  updatedAt?: string;
  url?: string;
}

interface GqlPrNode {
  number: number;
  title: string;
  url: string;
  state: 'OPEN' | 'CLOSED' | 'MERGED';
  isDraft: boolean;
  createdAt: string;
  updatedAt: string;
  headRefName: string;
  headRefOid: string;
  baseRefName: string;
  baseRefOid: string;
  commitCount?: { totalCount: number };
  body: string | null;
  additions: number;
  deletions: number;
  changedFiles: number;
  mergeable: PullRequest['mergeableStatus'];
  mergeStateStatus: PullRequest['mergeStateStatus'];
  author: GqlUser | null;
  headRepository: { url: string } | null;
  baseRepository: { url: string } | null;
  labels: { nodes: Array<{ name: string; color: string }> };
  assignees: { nodes: GqlUser[] };
  reviewDecision: string | null;
}

interface GqlCheckRunNode {
  __typename: 'CheckRun';
  name: string;
  status: string;
  conclusion: string | null;
  detailsUrl: string | null;
  startedAt: string | null;
  completedAt: string | null;
  checkSuite: {
    app: { name: string; logoUrl: string } | null;
    workflowRun: { workflow: { name: string } } | null;
  } | null;
}

interface GqlStatusContextNode {
  __typename: 'StatusContext';
  context: string;
  state: string;
  targetUrl: string | null;
  createdAt: string;
}

type GqlCheckNode = GqlCheckRunNode | GqlStatusContextNode;

export class PullRequestEngine {
  private readonly requestLanes = new Map<string, RequestLane>();
  /**
   * Last identity each repository was accessed as, keyed by repository URL and
   * held in memory only — the store no longer persists an account binding.
   * Cursors track what one identity has seen, so an identity change invalidates
   * them; the next sync rebuilds the repository's view from scratch.
   */
  private readonly lastAccessIdentities = new Map<string, string>();

  constructor(private readonly options: PullRequestEngineOptions) {}

  async sync(
    repositoryUrl: string,
    signal: AbortSignal,
    priority: number = requestPriorities.task
  ): Promise<Result<void, PullRequestError>> {
    const fullCursor = this.options.store.getCursor(repositoryUrl, 'full');
    return fullCursor?.done
      ? await this.runIncrementalSync(repositoryUrl, signal, priority)
      : await this.runFullSync(repositoryUrl, signal, priority);
  }

  async forceFullSync(
    repositoryUrl: string,
    signal: AbortSignal,
    priority: number = requestPriorities.task
  ): Promise<Result<void, PullRequestError>> {
    this.options.store.clearCursors(repositoryUrl);
    return await this.runFullSync(repositoryUrl, signal, priority);
  }

  async syncSingle(
    repositoryUrl: string,
    number: number,
    signal: AbortSignal,
    options: { emit?: boolean } = {}
  ): Promise<Result<PullRequest, PullRequestError>> {
    const emitProgress = options.emit !== false;
    const repository = this.parseRepository(repositoryUrl);
    if (!repository.success) return repository;
    const github = await this.getOctokit(repository.data, signal);
    if (!github.success) {
      if (emitProgress) {
        this.emit(repositoryUrl, {
          phase: 'error',
          kind: 'single',
          error: github.error,
        });
      }
      return github;
    }
    const { lane, octokit } = github.data;
    if (emitProgress) {
      this.emit(repositoryUrl, { phase: 'running', kind: 'single', synced: 0 });
    }
    try {
      const response = await this.request(
        lane,
        signal,
        {
          priority: requestPriorities.interactive,
          key: `pr:${repository.data.repositoryUrl}:${number}`,
        },
        (requestSignal) =>
          octokit.graphql<{
            repository: { pullRequest: GqlPrNode | null };
            rateLimit?: GraphQlRateLimit;
          }>(GET_PR_BY_NUMBER_QUERY, {
            owner: repository.data.owner,
            repo: repository.data.repo,
            number,
            request: { signal: requestSignal },
          })
      );
      lane.gates.graphql.observe(graphQlRateFeedback(response.rateLimit));
      const node = response.repository.pullRequest;
      if (!node) {
        const notFound: PullRequestError = {
          type: 'github_not_found_or_no_access',
          host: repository.data.host,
          message: `Pull request #${number} was not found`,
        };
        if (emitProgress) {
          this.emit(repositoryUrl, {
            phase: 'error',
            kind: 'single',
            error: notFound,
          });
        }
        return err(notFound);
      }
      const pr = this.saveNode(repositoryUrl, node);
      this.emit(repositoryUrl, {
        phase: 'idle',
        kind: 'single',
        synced: 1,
        lastSyncedAt: Date.now(),
      });
      return ok(pr);
    } catch (error) {
      if (signal.aborted || isAbortError(error)) {
        if (emitProgress) {
          this.emit(repositoryUrl, { phase: 'idle', kind: 'single' });
        }
        return err({ type: 'refresh_failed', message: 'Operation cancelled' });
      }
      const result = this.handleError<PullRequest>(
        error,
        repository.data,
        'Unable to refresh pull request',
        'refresh_failed'
      );
      if (!result.success && emitProgress) {
        this.emit(repositoryUrl, {
          phase: 'error',
          kind: 'single',
          error: result.error,
        });
      }
      return result;
    }
  }

  async syncChecks(
    repositoryUrl: string,
    pullRequestUrl: string,
    headRefOid: string,
    signal: AbortSignal
  ): Promise<Result<boolean, PullRequestError>> {
    const repository = this.parseRepository(repositoryUrl);
    if (!repository.success) return repository;
    const identity = this.options.store.getPullRequestIdentity(pullRequestUrl);
    const number = identity?.identifier
      ? Number.parseInt(identity.identifier.replace('#', ''), 10)
      : Number.NaN;
    if (!Number.isFinite(number)) return ok(false);
    if (this.options.store.getChecksCommitSha(pullRequestUrl) !== headRefOid) {
      this.options.store.clearChecks(pullRequestUrl);
    }
    const github = await this.getOctokit(repository.data, signal);
    if (!github.success) return github;
    const { lane, octokit } = github.data;
    try {
      const nodes: GqlCheckNode[] = [];
      let cursor: string | undefined;
      for (;;) {
        const response = await this.request(
          lane,
          signal,
          {
            priority: requestPriorities.interactive,
            key: `checks:${repository.data.repositoryUrl}:${number}:${headRefOid}:${cursor ?? ''}`,
          },
          (requestSignal) =>
            octokit.graphql<{
              repository: {
                pullRequest: {
                  commits: {
                    nodes: Array<{
                      commit: {
                        statusCheckRollup: {
                          contexts: {
                            pageInfo: { hasNextPage: boolean; endCursor: string | null };
                            nodes: GqlCheckNode[];
                          };
                        } | null;
                      };
                    }>;
                  };
                } | null;
              };
              rateLimit?: GraphQlRateLimit;
            }>(GET_PR_CHECK_RUNS_BY_URL_QUERY, {
              owner: repository.data.owner,
              repo: repository.data.repo,
              number,
              cursor: cursor ?? null,
              request: { signal: requestSignal },
            })
        );
        lane.gates.graphql.observe(graphQlRateFeedback(response.rateLimit));
        const contexts =
          response.repository.pullRequest?.commits.nodes[0]?.commit.statusCheckRollup?.contexts;
        if (!contexts) break;
        nodes.push(...contexts.nodes);
        if (!contexts.pageInfo.hasNextPage) break;
        cursor = contexts.pageInfo.endCursor ?? undefined;
      }
      this.options.store.replaceChecks(
        pullRequestUrl,
        nodes.map((node, index) =>
          checkNodeToPullRequestCheck(node, pullRequestUrl, headRefOid, index)
        )
      );
      this.emit(repositoryUrl, {
        phase: 'idle',
        kind: 'single',
        lastSyncedAt: Date.now(),
      });
      return ok(
        nodes.some((node) =>
          node.__typename === 'CheckRun'
            ? ['IN_PROGRESS', 'QUEUED', 'WAITING', 'PENDING'].includes(node.status)
            : node.state === 'PENDING'
        )
      );
    } catch (error) {
      return this.handleError(error, repository.data, 'Unable to sync check runs', 'checks_failed');
    }
  }

  async createPullRequest(
    input: {
      repositoryUrl: string;
      headRepositoryUrl?: string;
      head: string;
      base: string;
      title: string;
      body?: string;
      draft: boolean;
    },
    signal: AbortSignal
  ): Promise<Result<{ url: string; number: number }, PullRequestError>> {
    const repository = this.parseRepository(input.repositoryUrl);
    if (!repository.success) return repository;
    if (input.headRepositoryUrl) {
      const head = parseRepositoryRef(input.headRepositoryUrl);
      if (head && head.host !== repository.data.host) {
        return err({
          type: 'cross_host_pr',
          baseHost: repository.data.host,
          headHost: head.host,
        });
      }
    }
    const github = await this.getOctokit(repository.data, signal);
    if (!github.success) return github;
    const { lane, octokit } = github.data;
    try {
      const response = await this.request(
        lane,
        signal,
        { priority: requestPriorities.interactive },
        (requestSignal) =>
          octokit.rest.pulls.create({
            owner: repository.data.owner,
            repo: repository.data.repo,
            head: input.head,
            base: input.base,
            title: input.title,
            body: input.body,
            draft: input.draft,
            request: { signal: requestSignal },
          })
      );
      return ok({ url: response.data.html_url, number: response.data.number });
    } catch (error) {
      return this.handleError(
        error,
        repository.data,
        'Unable to create pull request',
        'create_failed'
      );
    }
  }

  async mergePullRequest(
    repositoryUrl: string,
    number: number,
    options: PullRequestMergeOptions,
    signal: AbortSignal
  ): Promise<Result<{ sha: string | null; merged: boolean }, PullRequestError>> {
    const repository = this.parseRepository(repositoryUrl);
    if (!repository.success) return repository;
    const github = await this.getOctokit(repository.data, signal);
    if (!github.success) return github;
    const { lane, octokit } = github.data;
    try {
      const response = await this.request(
        lane,
        signal,
        { priority: requestPriorities.interactive },
        (requestSignal) =>
          octokit.rest.pulls.merge({
            owner: repository.data.owner,
            repo: repository.data.repo,
            pull_number: number,
            merge_method: options.strategy,
            sha: options.commitHeadOid,
            request: { signal: requestSignal },
          })
      );
      return ok({ sha: response.data.sha ?? null, merged: response.data.merged });
    } catch (error) {
      return this.handleError(
        error,
        repository.data,
        'Unable to merge pull request',
        'merge_failed'
      );
    }
  }

  async markReadyForReview(
    repositoryUrl: string,
    number: number,
    signal: AbortSignal
  ): Promise<Result<void, PullRequestError>> {
    const repository = this.parseRepository(repositoryUrl);
    if (!repository.success) return repository;
    const github = await this.getOctokit(repository.data, signal);
    if (!github.success) return github;
    const { lane, octokit } = github.data;
    try {
      const response = await this.request(
        lane,
        signal,
        {
          priority: requestPriorities.interactive,
          key: `pr-node-id:${repository.data.repositoryUrl}:${number}`,
        },
        (requestSignal) =>
          octokit.rest.pulls.get({
            owner: repository.data.owner,
            repo: repository.data.repo,
            pull_number: number,
            request: { signal: requestSignal },
          })
      );
      await this.request(
        lane,
        signal,
        { priority: requestPriorities.interactive },
        (requestSignal) =>
          octokit.graphql(
            `mutation MarkReadyForReview($id: ID!) {
            markPullRequestReadyForReview(input: { pullRequestId: $id }) {
              pullRequest { isDraft }
            }
          }`,
            { id: response.data.node_id, request: { signal: requestSignal } }
          )
      );
      return ok();
    } catch (error) {
      return this.handleError(
        error,
        repository.data,
        'Unable to mark PR ready for review',
        'mark_ready_failed'
      );
    }
  }

  async getPullRequestComments(
    repositoryUrl: string,
    number: number,
    signal: AbortSignal
  ): Promise<Result<PullRequestComment[], PullRequestError>> {
    const repository = this.parseRepository(repositoryUrl);
    if (!repository.success) return repository;
    const pullRequestUrl = `${repository.data.repositoryUrl}/pull/${number}`;
    const canPersist = this.options.store.getPullRequestByUrl(pullRequestUrl) !== null;
    const state = canPersist ? this.options.store.getCommentState(pullRequestUrl) : null;
    const cachedComments = state ? this.options.store.getComments(pullRequestUrl) : [];
    const github = await this.getOctokit(repository.data, signal);
    if (!github.success) return state ? ok(cachedComments) : github;
    const { lane, octokit } = github.data;
    try {
      const pullRequestResponse = await this.request(
        lane,
        signal,
        {
          priority: requestPriorities.interactive,
          key: `comments:etag:${repository.data.repositoryUrl}:${number}`,
        },
        (requestSignal) =>
          octokit.rest.pulls.get({
            owner: repository.data.owner,
            repo: repository.data.repo,
            pull_number: number,
            ...(state?.etag ? { headers: { 'if-none-match': state.etag } } : {}),
            request: { signal: requestSignal },
          })
      );
      const comments = await this.fetchPullRequestComments(
        repository.data,
        github.data,
        pullRequestUrl,
        number,
        signal
      );
      if (canPersist) {
        this.options.store.replaceComments(pullRequestUrl, comments);
        this.options.store.setCommentState(
          pullRequestUrl,
          pullRequestResponse.headers.etag ?? null
        );
      }
      return ok(comments);
    } catch (error) {
      if (isNotModifiedError(error)) {
        if (state) this.options.store.setCommentState(pullRequestUrl, state.etag);
        return ok(cachedComments);
      }
      if (state) {
        this.options.logger.warn('Unable to refresh cached pull request comments', {
          repositoryUrl: repository.data.repositoryUrl,
          number,
          error: error instanceof Error ? error.message : String(error),
        });
        return ok(cachedComments);
      }
      return this.handleError(
        error,
        repository.data,
        'Unable to get pull request comments',
        'comments_failed'
      );
    }
  }

  private async fetchPullRequestComments(
    repository: RepositoryRef,
    github: GitHubClient,
    pullRequestUrl: string,
    number: number,
    signal: AbortSignal
  ): Promise<PullRequestComment[]> {
    const { lane, octokit } = github;
    const [issueComments, reviewComments, reviews] = await Promise.all([
      this.request(
        lane,
        signal,
        {
          priority: requestPriorities.interactive,
          key: `comments:issue:${repository.repositoryUrl}:${number}`,
        },
        (requestSignal) =>
          octokit.paginate(octokit.rest.issues.listComments, {
            owner: repository.owner,
            repo: repository.repo,
            issue_number: number,
            per_page: 100,
            request: { signal: requestSignal },
          })
      ),
      this.request(
        lane,
        signal,
        {
          priority: requestPriorities.interactive,
          key: `comments:review-comments:${repository.repositoryUrl}:${number}`,
        },
        (requestSignal) =>
          octokit.paginate(octokit.rest.pulls.listReviewComments, {
            owner: repository.owner,
            repo: repository.repo,
            pull_number: number,
            per_page: 100,
            request: { signal: requestSignal },
          })
      ),
      this.request(
        lane,
        signal,
        {
          priority: requestPriorities.interactive,
          key: `comments:reviews:${repository.repositoryUrl}:${number}`,
        },
        (requestSignal) =>
          octokit.paginate(octokit.rest.pulls.listReviews, {
            owner: repository.owner,
            repo: repository.repo,
            pull_number: number,
            per_page: 100,
            request: { signal: requestSignal },
          })
      ),
    ]);
    return [
      ...issueComments.map((comment) => ({
        id: `issue-comment:${comment.id}`,
        pullRequestUrl,
        kind: 'issue' as const,
        body: comment.body ?? '',
        url: comment.html_url,
        author: comment.user ? restUserToPullRequestUser(comment.user, repository.host) : null,
        path: null,
        line: null,
        isResolved: false,
        isOutdated: false,
        createdAt: comment.created_at,
        updatedAt: comment.updated_at,
      })),
      ...reviews.flatMap((review): PullRequestComment[] => {
        if (!review.body?.trim() || !review.submitted_at) return [];
        return [
          {
            id: `review:${review.id}`,
            pullRequestUrl,
            kind: 'review',
            body: review.body,
            url: review.html_url,
            author: review.user ? restUserToPullRequestUser(review.user, repository.host) : null,
            path: null,
            line: null,
            isResolved: false,
            isOutdated: false,
            createdAt: review.submitted_at,
            updatedAt: review.submitted_at,
          },
        ];
      }),
      ...reviewComments.map((comment) => ({
        id: `review-comment:${comment.id}`,
        pullRequestUrl,
        kind: 'review' as const,
        body: comment.body ?? '',
        url: comment.html_url,
        author: comment.user ? restUserToPullRequestUser(comment.user, repository.host) : null,
        path: comment.path ?? null,
        line: comment.line ?? comment.original_line ?? null,
        isResolved: false,
        isOutdated: comment.position == null,
        createdAt: comment.created_at,
        updatedAt: comment.updated_at,
      })),
    ];
  }

  async getPullRequestFiles(
    repositoryUrl: string,
    number: number,
    signal: AbortSignal
  ): Promise<Result<PullRequestFile[], PullRequestError>> {
    const repository = this.parseRepository(repositoryUrl);
    if (!repository.success) return repository;
    const github = await this.getOctokit(repository.data, signal);
    if (!github.success) return github;
    const { lane, octokit } = github.data;
    try {
      const files = await this.request(
        lane,
        signal,
        {
          priority: requestPriorities.interactive,
          key: `files:${repository.data.repositoryUrl}:${number}`,
        },
        (requestSignal) =>
          octokit.paginate(octokit.rest.pulls.listFiles, {
            owner: repository.data.owner,
            repo: repository.data.repo,
            pull_number: number,
            per_page: 100,
            request: { signal: requestSignal },
          })
      );
      return ok(
        files.map((file) => ({
          filename: file.filename,
          status: file.status,
          additions: file.additions,
          deletions: file.deletions,
          patch: file.patch,
        }))
      );
    } catch (error) {
      return this.handleError(
        error,
        repository.data,
        'Unable to get pull request files',
        'files_failed'
      );
    }
  }

  private async runFullSync(
    repositoryUrl: string,
    signal: AbortSignal,
    priority: number
  ): Promise<Result<void, PullRequestError>> {
    const repository = this.parseRepository(repositoryUrl);
    if (!repository.success) return repository;
    const github = await this.getOctokit(repository.data, signal);
    if (!github.success) {
      this.emit(repositoryUrl, {
        phase: 'error',
        kind: 'full',
        error: github.error,
      });
      return github;
    }
    const { lane, octokit } = github.data;
    const existing = this.options.store.getCursor(repositoryUrl, 'full');
    let pageCursor = existing?.done ? undefined : existing?.pageCursor;
    let synced = 0;
    this.emit(repositoryUrl, { phase: 'running', kind: 'full', synced: 0 });
    try {
      for (;;) {
        const response = await this.request(
          lane,
          signal,
          {
            priority,
            key: `sync:full:${repositoryUrl}:${pageCursor ?? ''}`,
          },
          (requestSignal) =>
            octokit.graphql<{
              repository: {
                pullRequests: {
                  totalCount: number;
                  pageInfo: { hasNextPage: boolean; endCursor: string | null };
                  nodes: GqlPrNode[];
                };
              };
              rateLimit?: GraphQlRateLimit;
            }>(SYNC_PRS_QUERY, {
              owner: repository.data.owner,
              repo: repository.data.repo,
              cursor: pageCursor ?? null,
              request: { signal: requestSignal },
            })
        );
        lane.gates.graphql.observe(graphQlRateFeedback(response.rateLimit));
        const { nodes, pageInfo, totalCount } = response.repository.pullRequests;
        for (const node of nodes) this.saveNode(repositoryUrl, node);
        synced += nodes.length;
        const done =
          !pageInfo.hasNextPage || synced >= (this.options.maxSyncCount ?? DEFAULT_MAX_SYNC_COUNT);
        const cursor: SyncCursor = {
          lastUpdatedAt:
            this.options.store.getNewestPullRequestUpdatedAt(repositoryUrl) ??
            existing?.lastUpdatedAt ??
            new Date().toISOString(),
          pageCursor: done ? undefined : (pageInfo.endCursor ?? undefined),
          done,
        };
        this.options.store.setCursor(repositoryUrl, 'full', cursor);
        this.emit(repositoryUrl, {
          phase: 'running',
          kind: 'full',
          synced,
          total: Math.min(totalCount, this.options.maxSyncCount ?? DEFAULT_MAX_SYNC_COUNT),
        });
        if (done) break;
        pageCursor = pageInfo.endCursor ?? undefined;
      }
      this.archiveOld(repositoryUrl);
      this.emit(repositoryUrl, {
        phase: 'idle',
        kind: 'full',
        synced,
        lastSyncedAt: Date.now(),
      });
      return ok();
    } catch (error) {
      return this.handleSyncError(error, repositoryUrl, repository.data, 'full', signal);
    }
  }

  private async runIncrementalSync(
    repositoryUrl: string,
    signal: AbortSignal,
    priority: number
  ): Promise<Result<void, PullRequestError>> {
    const repository = this.parseRepository(repositoryUrl);
    if (!repository.success) return repository;
    const github = await this.getOctokit(repository.data, signal);
    if (!github.success) {
      this.emit(repositoryUrl, {
        phase: 'error',
        kind: 'incremental',
        error: github.error,
      });
      return github;
    }
    const { lane, octokit } = github.data;
    const fullCursor = this.options.store.getCursor(repositoryUrl, 'full');
    const existing = this.options.store.getCursor(repositoryUrl, 'incremental');
    const boundary =
      existing?.lastUpdatedAt ?? fullCursor?.lastUpdatedAt ?? new Date(0).toISOString();
    let pageCursor = existing?.done ? undefined : existing?.pageCursor;
    let synced = 0;
    this.emit(repositoryUrl, { phase: 'running', kind: 'incremental', synced: 0 });
    try {
      for (;;) {
        const response = await this.request(
          lane,
          signal,
          {
            priority,
            key: `sync:incremental:${repositoryUrl}:${pageCursor ?? ''}`,
          },
          (requestSignal) =>
            octokit.graphql<{
              repository: {
                pullRequests: {
                  pageInfo: { hasNextPage: boolean; endCursor: string | null };
                  nodes: GqlPrNode[];
                };
              };
              rateLimit?: GraphQlRateLimit;
            }>(INCREMENTAL_SYNC_PRS_QUERY, {
              owner: repository.data.owner,
              repo: repository.data.repo,
              cursor: pageCursor ?? null,
              request: { signal: requestSignal },
            })
        );
        lane.gates.graphql.observe(graphQlRateFeedback(response.rateLimit));
        const { nodes, pageInfo } = response.repository.pullRequests;
        const batch = nodes.filter((node) => node.updatedAt >= boundary);
        const reachedBoundary = batch.length !== nodes.length;
        for (const node of batch) this.saveNode(repositoryUrl, node);
        synced += batch.length;
        if (synced >= (this.options.maxSyncCount ?? DEFAULT_MAX_SYNC_COUNT)) {
          // The repository is too far behind for an incremental update; the next sync rebuilds it.
          this.options.store.clearCursors(repositoryUrl);
          break;
        }
        const done = reachedBoundary || !pageInfo.hasNextPage;
        this.options.store.setCursor(repositoryUrl, 'incremental', {
          lastUpdatedAt: done
            ? (this.options.store.getNewestPullRequestUpdatedAt(repositoryUrl) ?? boundary)
            : boundary,
          pageCursor: done ? undefined : (pageInfo.endCursor ?? undefined),
          done,
        });
        this.emit(repositoryUrl, { phase: 'running', kind: 'incremental', synced });
        if (done) break;
        pageCursor = pageInfo.endCursor ?? undefined;
      }
      this.emit(repositoryUrl, {
        phase: 'idle',
        kind: 'incremental',
        synced,
        lastSyncedAt: Date.now(),
      });
      return ok();
    } catch (error) {
      return this.handleSyncError(error, repositoryUrl, repository.data, 'incremental', signal);
    }
  }

  private saveNode(repositoryUrl: string, node: GqlPrNode): PullRequest {
    const previous = this.options.store.getPullRequestByUrl(node.url);
    const baseRepository =
      parseRepositoryRef(node.baseRepository?.url ?? '') ?? parseRepositoryRef(repositoryUrl);
    const baseRepositoryUrl = baseRepository?.repositoryUrl ?? repositoryUrl;
    const repositoryHost = baseRepository?.host ?? 'unknown';
    const headRepositoryUrl =
      parseRepositoryRef(node.headRepository?.url ?? '')?.repositoryUrl ?? repositoryUrl;
    return this.options.store.savePullRequest({
      url: node.url,
      provider: 'github',
      repositoryUrl: baseRepositoryUrl,
      baseRefName: node.baseRefName,
      baseRefOid: node.baseRefOid,
      headRepositoryUrl,
      headRefName: node.headRefName,
      headRefOid: node.headRefOid,
      identifier: `#${node.number}`,
      title: node.title,
      description: node.body,
      status: node.state === 'MERGED' ? 'merged' : node.state === 'CLOSED' ? 'closed' : 'open',
      isDraft: node.isDraft,
      additions: node.additions,
      deletions: node.deletions,
      changedFiles: node.changedFiles,
      commitCount: node.commitCount?.totalCount ?? null,
      mergeableStatus: node.mergeable,
      mergeStateStatus: node.mergeStateStatus,
      reviewDecision: node.reviewDecision,
      createdAt: node.createdAt,
      updatedAt: node.updatedAt,
      author: node.author ? gqlUserToPullRequestUser(node.author, repositoryHost) : null,
      labels: node.labels.nodes.map((label) => ({ name: label.name, color: label.color ?? null })),
      assignees: node.assignees.nodes.map((user) => gqlUserToPullRequestUser(user, repositoryHost)),
      checks: previous?.checks ?? [],
    });
  }

  private archiveOld(repositoryUrl: string): void {
    const cutoff = new Date();
    cutoff.setMonth(
      cutoff.getMonth() - (this.options.archiveAgeMonths ?? DEFAULT_ARCHIVE_AGE_MONTHS)
    );
    this.options.store.archiveOldPullRequests(repositoryUrl, cutoff.toISOString());
  }

  private async getOctokit(
    repository: RepositoryRef,
    signal: AbortSignal
  ): Promise<Result<GitHubClient, PullRequestError>> {
    const registered = this.options.store.getRegisteredRepository(repository.repositoryUrl);
    if (!registered) {
      return err({
        type: 'repository_not_registered',
        repositoryUrl: repository.repositoryUrl,
      });
    }
    // Identity is a per-request runtime parameter (spec: github-git-settings §8):
    // the desktop resolves "as whom" through the blessed resolver on every call,
    // so account changes apply on the very next sync with no event plumbing.
    const auth = await this.options.githubAuth.resolveAuth(
      { repositoryUrl: repository.repositoryUrl },
      { signal }
    );
    if (!auth.success) return err(mapAuthError(auth.error));
    this.resetCursorsOnIdentityChange(repository.repositoryUrl, auth.data.accountId);
    const lane = this.getRequestLane(repository.host, auth.data.accountId);
    const octokit =
      this.options.createOctokit?.({
        token: auth.data.token,
        baseUrl: auth.data.apiBaseUrl,
      }) ??
      new Octokit({
        auth: auth.data.token,
        baseUrl: auth.data.apiBaseUrl,
        log: {
          debug: () => this.options.logger.debug('Octokit request'),
          info: () => this.options.logger.debug('Octokit request completed'),
          warn: () => this.options.logger.warn('Octokit request warning'),
          error: () => this.options.logger.warn('Octokit request failed'),
        },
      });
    this.observeOctokitRateLimits(octokit, lane);
    return ok({ octokit, lane });
  }

  private resetCursorsOnIdentityChange(repositoryUrl: string, accountId: string | undefined): void {
    const identity = accountId ?? '';
    const previous = this.lastAccessIdentities.get(repositoryUrl);
    if (previous !== undefined && previous !== identity) {
      this.options.store.clearCursors(repositoryUrl);
    }
    this.lastAccessIdentities.set(repositoryUrl, identity);
  }

  private parseRepository(repositoryUrl: string): Result<RepositoryRef, PullRequestError> {
    const repository = parseRepositoryRef(repositoryUrl);
    return repository ? ok(repository) : err({ type: 'invalid_repository', input: repositoryUrl });
  }

  private async request<T>(
    lane: RequestLane,
    signal: AbortSignal,
    options: RequestOptions,
    operation: (signal: AbortSignal) => Promise<T>
  ): Promise<T> {
    return await retry(
      async () =>
        await lane.scheduler.submit(
          {
            priority: options.priority,
            cost: options.cost ?? 0,
            key: options.key,
            run: operation,
          },
          { signal }
        ),
      {
        signal,
        schedule: this.options.retrySchedule ?? defaultRetrySchedule,
        shouldRetry: isRetryableRequestError,
      }
    );
  }

  private getRequestLane(host: string, accountId: string | undefined): RequestLane {
    const key = `${host}\u0000${accountId ?? 'default'}`;
    const existing = this.requestLanes.get(key);
    if (existing) return existing;
    const gates = {
      graphql: this.createRateGate('graphql'),
      rest: this.createRateGate('rest'),
    };
    const scheduler = (this.options.createScheduler ?? createRequestScheduler)({
      scope: this.options.scope,
      maxConcurrency: DEFAULT_REQUEST_CONCURRENCY,
      label: `github:${host}:${accountId ?? 'default'}`,
    });
    const lane = { gates, scheduler };
    this.requestLanes.set(key, lane);
    return lane;
  }

  private createRateGate(resource: GitHubRateResource): RateGate {
    return (
      this.options.createRateGate?.(resource) ??
      createTokenBucketGate({
        capacity: DEFAULT_REQUEST_CAPACITY,
        refillPerSec: DEFAULT_REQUEST_REFILL_PER_SEC,
        reserve: DEFAULT_REQUEST_RESERVE,
      })
    );
  }

  private observeOctokitRateLimits(octokit: Octokit, lane: RequestLane): void {
    const hook = (octokit as unknown as { hook?: OctokitRequestHook }).hook;
    if (!hook) return;
    hook.before?.('request', async (options) => {
      const resource = rateResourceForRequest(options);
      await lane.gates[resource].acquire(
        resource === 'graphql' ? 0 : 1,
        options.request?.signal ?? this.options.scope.signal
      );
    });
    hook.after('request', (response, options) => {
      const resource = rateResourceForRequest(options, response.headers);
      lane.gates[resource].observe(rateFeedbackFromHeaders(response.headers));
    });
    hook.error('request', (error, options) => {
      const headers = responseHeadersFromError(error);
      const resource = rateResourceForRequest(options, headers);
      lane.gates[resource].observe(rateFeedbackFromHeaders(headers));
      throw error;
    });
  }

  private handleError<T>(
    error: unknown,
    repository: RepositoryRef,
    fallback: string,
    operationType: PullRequestOperationErrorType
  ): Result<T, PullRequestError> {
    return err(
      mapApiError(error, fallback, repository.host, repository.nameWithOwner, operationType)
    );
  }

  private handleSyncError(
    error: unknown,
    repositoryUrl: string,
    repository: RepositoryRef,
    kind: 'full' | 'incremental',
    signal: AbortSignal
  ): Result<void, PullRequestError> {
    if (signal.aborted || isAbortError(error)) {
      this.emit(repositoryUrl, { phase: 'idle', kind });
      return err({ type: 'sync_failed', message: 'Pull request sync cancelled' });
    }
    const mapped = mapApiError(
      error,
      'Unable to sync pull requests',
      repository.host,
      repository.nameWithOwner
    );
    this.options.logger.warn('Pull request sync failed', {
      repositoryUrl,
      error: mapped,
    });
    this.emit(repositoryUrl, {
      phase: 'error',
      kind,
      error: mapped,
    });
    return err(mapped);
  }

  private emit(repositoryUrl: string, state: SyncState): void {
    this.options.onSyncState?.(repositoryUrl, state);
  }
}

function gqlUserToPullRequestUser(user: GqlUser, host: string): PullRequestUser {
  return {
    userId: user.databaseId == null ? `${host}:login:${user.login}` : `${host}:${user.databaseId}`,
    userName: user.login,
    displayName: user.login,
    avatarUrl: user.avatarUrl || null,
    url: user.url ?? null,
    userCreatedAt: user.createdAt ?? null,
    userUpdatedAt: user.updatedAt ?? null,
  };
}

function restUserToPullRequestUser(
  user: {
    id: number;
    login: string;
    avatar_url: string;
    html_url: string;
  },
  host: string
): PullRequestUser {
  return {
    userId: `${host}:${user.id}`,
    userName: user.login,
    displayName: user.login,
    avatarUrl: user.avatar_url || null,
    url: user.html_url,
    userCreatedAt: null,
    userUpdatedAt: null,
  };
}

function checkNodeToPullRequestCheck(
  node: GqlCheckNode,
  pullRequestUrl: string,
  headRefOid: string,
  index: number
): PullRequestCheck {
  if (node.__typename === 'CheckRun') {
    return {
      id: `${headRefOid}:${index}:${node.name}`,
      pullRequestUrl,
      commitSha: headRefOid,
      name: node.name,
      status: node.status,
      conclusion: node.conclusion ?? 'NEUTRAL',
      detailsUrl: node.detailsUrl,
      startedAt: node.startedAt,
      completedAt: node.completedAt,
      workflowName: node.checkSuite?.workflowRun?.workflow.name ?? null,
      appName: node.checkSuite?.app?.name ?? null,
      appLogoUrl: node.checkSuite?.app?.logoUrl ?? null,
    };
  }
  return {
    id: `${headRefOid}:${index}:${node.context}`,
    pullRequestUrl,
    commitSha: headRefOid,
    name: node.context,
    status: node.state === 'PENDING' ? 'IN_PROGRESS' : 'COMPLETED',
    conclusion:
      node.state === 'SUCCESS'
        ? 'SUCCESS'
        : node.state === 'FAILURE' || node.state === 'ERROR'
          ? 'FAILURE'
          : 'NEUTRAL',
    detailsUrl: node.targetUrl,
    startedAt: node.createdAt,
    completedAt: node.state === 'PENDING' ? null : node.createdAt,
    workflowName: null,
    appName: null,
    appLogoUrl: null,
  };
}

function isRetryableRequestError(error: unknown): boolean {
  const status =
    typeof error === 'object' && error !== null && 'status' in error
      ? Number((error as { status?: unknown }).status)
      : undefined;
  return status === 429 || (status !== undefined && status >= 500) || isNetworkError(error);
}

function isNotModifiedError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'status' in error &&
    Number((error as { status?: unknown }).status) === 304
  );
}

function graphQlRateFeedback(rateLimit: GraphQlRateLimit | undefined): RateFeedback {
  if (!rateLimit) return {};
  const resetAtMs = Date.parse(rateLimit.resetAt);
  return {
    cost: rateLimit.cost,
    remaining: rateLimit.remaining,
    resetAtMs: Number.isFinite(resetAtMs) ? resetAtMs : undefined,
  };
}

function responseHeadersFromError(error: unknown): OctokitHeaders | undefined {
  if (typeof error !== 'object' || error === null || !('response' in error)) return undefined;
  return (error as { response?: { headers?: OctokitHeaders } }).response?.headers;
}

function rateResourceForRequest(
  options: OctokitRequestOptions,
  headers?: OctokitHeaders
): GitHubRateResource {
  const resource = String(headers?.['x-ratelimit-resource'] ?? '').toLowerCase();
  if (resource === 'graphql') return 'graphql';
  if (resource) return 'rest';
  return options.url?.includes('/graphql') ? 'graphql' : 'rest';
}

function rateFeedbackFromHeaders(headers: OctokitHeaders | undefined): RateFeedback {
  if (!headers) return {};
  const remaining = parseFiniteHeader(headers, 'x-ratelimit-remaining');
  const resetSeconds = parseFiniteHeader(headers, 'x-ratelimit-reset');
  const retryAfter = headers['retry-after'];
  return {
    remaining,
    resetAtMs: resetSeconds === undefined ? undefined : resetSeconds * 1_000,
    retryAfterMs: retryAfterMs(retryAfter),
  };
}

function parseFiniteHeader(headers: OctokitHeaders, name: string): number | undefined {
  const value = Number(headers[name]);
  return Number.isFinite(value) && value >= 0 ? value : undefined;
}

function retryAfterMs(value: string | number | undefined): number | undefined {
  if (value === undefined) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1_000;
  const date = Date.parse(String(value));
  return Number.isFinite(date) ? Math.max(0, date - Date.now()) : undefined;
}
