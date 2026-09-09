import { randomUUID } from 'node:crypto';
import type { SqliteConnection, StoreHandle } from '@emdash/core/primitives/sqlite-store/api';
import type {
  ListPullRequestsInput,
  PullRequest,
  PullRequestCheck,
  PullRequestComment,
  PullRequestFilterOptions,
  PullRequestLabel,
  PullRequestUser,
} from '../../api';

export type SyncCursorKind = 'full' | 'incremental';

export type SyncCursor = {
  lastUpdatedAt: string;
  pageCursor?: string;
  done: boolean;
};

export type RegisteredRepository = {
  id: string;
  repositoryUrl: string;
};

type PullRequestDbRow = {
  url: string;
  provider: string;
  repositoryUrl: string;
  baseRefName: string;
  baseRefOid: string;
  headRepositoryUrl: string;
  headRefName: string;
  headRefOid: string;
  identifier: string | null;
  title: string;
  description: string | null;
  status: PullRequest['status'];
  isDraft: number;
  authorUserId: string | null;
  additions: number | null;
  deletions: number | null;
  changedFiles: number | null;
  commitCount: number | null;
  mergeableStatus: PullRequest['mergeableStatus'];
  mergeStateStatus: PullRequest['mergeStateStatus'];
  reviewDecision: string | null;
  createdAt: string;
  updatedAt: string;
};

type PullRequestUserDbRow = {
  userId: string;
  userName: string;
  displayName: string | null;
  avatarUrl: string | null;
  url: string | null;
  userUpdatedAt: string | null;
  userCreatedAt: string | null;
};

type PullRequestCommentDbRow = {
  id: string;
  pullRequestUrl: string;
  kind: PullRequestComment['kind'];
  body: string;
  url: string;
  authorUserId: string | null;
  path: string | null;
  line: number | null;
  isResolved: number;
  isOutdated: number;
  createdAt: string;
  updatedAt: string;
};

export type PullRequestCommentState = {
  etag: string | null;
  lastFetchedAt: number;
};

export class PullRequestStore {
  constructor(private readonly handle: StoreHandle<SqliteConnection>) {}

  registerRepository(repositoryUrl: string): RegisteredRepository {
    const now = Date.now();
    const existing = this.handle.connection.get<{ id: string }>(
      `SELECT id
      FROM registered_repositories
      WHERE repository_url = ?`,
      [repositoryUrl]
    );
    const id = existing?.id ?? randomUUID();
    this.handle.connection.run(
      `INSERT INTO registered_repositories (
        id, repository_url, created_at, updated_at
      ) VALUES (?, ?, ?, ?)
      ON CONFLICT(repository_url) DO UPDATE SET
        updated_at = excluded.updated_at`,
      [id, repositoryUrl, now, now]
    );
    return { id, repositoryUrl };
  }

  unregisterRepository(repositoryUrl: string): void {
    this.handle.transaction(() => {
      this.handle.connection.run('DELETE FROM registered_repositories WHERE repository_url = ?', [
        repositoryUrl,
      ]);
      this.handle.connection.run(
        `DELETE FROM pull_requests
        WHERE repository_url NOT IN (SELECT repository_url FROM registered_repositories)
          AND head_repository_url NOT IN (SELECT repository_url FROM registered_repositories)`
      );
      this.pruneOrphanUsers();
    });
  }

  getRegisteredRepository(repositoryUrl: string): RegisteredRepository | null {
    return (
      this.handle.connection.get<RegisteredRepository>(
        `SELECT
          id,
          repository_url AS repositoryUrl
        FROM registered_repositories
        WHERE repository_url = ?`,
        [repositoryUrl]
      ) ?? null
    );
  }

  listRegisteredRepositories(): RegisteredRepository[] {
    return this.handle.connection.all<RegisteredRepository>(
      `SELECT
        id,
        repository_url AS repositoryUrl
      FROM registered_repositories
      ORDER BY repository_url`
    );
  }

  getCursor(repositoryUrl: string, kind: SyncCursorKind): SyncCursor | null {
    const row = this.handle.connection.get<{
      lastUpdatedAt: string;
      pageCursor: string | null;
      done: number;
    }>(
      `SELECT
        cursor.last_updated_at AS lastUpdatedAt,
        cursor.page_cursor AS pageCursor,
        cursor.done AS done
      FROM sync_cursors cursor
      INNER JOIN registered_repositories repository
        ON repository.id = cursor.repository_id
      WHERE repository.repository_url = ? AND cursor.kind = ?`,
      [repositoryUrl, kind]
    );
    return row
      ? {
          lastUpdatedAt: row.lastUpdatedAt,
          pageCursor: row.pageCursor ?? undefined,
          done: Boolean(row.done),
        }
      : null;
  }

  setCursor(repositoryUrl: string, kind: SyncCursorKind, cursor: SyncCursor): void {
    const repository = this.requireRegisteredRepository(repositoryUrl);
    this.handle.connection.run(
      `INSERT INTO sync_cursors (
        repository_id, kind, last_updated_at, page_cursor, done
      ) VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(repository_id, kind) DO UPDATE SET
        last_updated_at = excluded.last_updated_at,
        page_cursor = excluded.page_cursor,
        done = excluded.done`,
      [repository.id, kind, cursor.lastUpdatedAt, cursor.pageCursor ?? null, cursor.done ? 1 : 0]
    );
  }

  clearCursors(repositoryUrl: string): void {
    const repository = this.getRegisteredRepository(repositoryUrl);
    if (!repository) return;
    this.handle.connection.run('DELETE FROM sync_cursors WHERE repository_id = ?', [repository.id]);
  }

  listPullRequests(input: ListPullRequestsInput): {
    prs: PullRequest[];
    nextCursor: string | null;
  } {
    const offset = decodeListCursor(input.cursor);
    const params: unknown[] = [];
    const repositoryPlaceholders = placeholders(input.repositoryUrls.length);
    params.push(...input.repositoryUrls, ...input.repositoryUrls, ...input.repositoryUrls);
    const conditions = [
      `(repository_url IN (${repositoryPlaceholders})
        OR head_repository_url IN (${repositoryPlaceholders}))`,
      `EXISTS (
        SELECT 1 FROM registered_repositories registered
        WHERE registered.repository_url IN (${repositoryPlaceholders})
          AND (
            registered.repository_url = pull_requests.repository_url
            OR registered.repository_url = pull_requests.head_repository_url
          )
      )`,
    ];

    if (input.filters?.status && input.filters.status !== 'all') {
      if (input.filters.status === 'not-open') {
        conditions.push("status IN ('closed', 'merged')");
      } else {
        conditions.push('status = ?');
        params.push(input.filters.status);
      }
    }
    if (input.filters?.authorUserIds?.length) {
      conditions.push(`author_user_id IN (${placeholders(input.filters.authorUserIds.length)})`);
      params.push(...input.filters.authorUserIds);
    }
    if (input.filters?.labelNames?.length) {
      conditions.push(
        `EXISTS (
          SELECT 1 FROM pull_request_labels label
          WHERE label.pull_request_url = pull_requests.url
            AND label.name IN (${placeholders(input.filters.labelNames.length)})
        )`
      );
      params.push(...input.filters.labelNames);
    }
    if (input.filters?.assigneeUserIds?.length) {
      conditions.push(
        `EXISTS (
          SELECT 1 FROM pull_request_assignees assignee
          WHERE assignee.pull_request_url = pull_requests.url
            AND assignee.user_id IN (${placeholders(input.filters.assigneeUserIds.length)})
        )`
      );
      params.push(...input.filters.assigneeUserIds);
    }
    if (input.searchQuery?.trim()) {
      const query = `%${input.searchQuery.trim()}%`;
      conditions.push('(title LIKE ? OR identifier LIKE ? OR head_ref_name LIKE ?)');
      params.push(query, query, query);
    }

    const orderBy =
      input.sort === 'oldest'
        ? 'pull_request_created_at ASC, url ASC'
        : input.sort === 'recently-updated'
          ? 'pull_request_updated_at DESC, url ASC'
          : 'pull_request_created_at DESC, url ASC';
    params.push(input.limit + 1, offset);
    const rows = this.handle.connection.all<PullRequestDbRow>(
      `${pullRequestSelectSql}
      WHERE ${conditions.join(' AND ')}
      ORDER BY ${orderBy}
      LIMIT ? OFFSET ?`,
      params
    );
    const hasMore = rows.length > input.limit;
    const page = hasMore ? rows.slice(0, input.limit) : rows;
    return {
      prs: this.assembleRows(page),
      nextCursor: hasMore ? encodeListCursor(offset + input.limit) : null,
    };
  }

  getPullRequestsForBranch(repositoryUrl: string, branch: string): PullRequest[] {
    const rows = this.handle.connection.all<PullRequestDbRow>(
      `${pullRequestSelectSql}
      WHERE head_ref_name = ?
        AND (repository_url = ? OR head_repository_url = ?)
        AND EXISTS (
          SELECT 1 FROM registered_repositories
          WHERE repository_url = ?
        )
      ORDER BY pull_request_created_at DESC`,
      [branch, repositoryUrl, repositoryUrl, repositoryUrl]
    );
    return this.assembleRows(rows);
  }

  getFilterOptions(repositoryUrls: string[]): PullRequestFilterOptions {
    if (repositoryUrls.length === 0) return { authors: [], labels: [], assignees: [] };
    const repositoryPlaceholders = placeholders(repositoryUrls.length);
    const scope = `(pr.repository_url IN (${repositoryPlaceholders})
      OR pr.head_repository_url IN (${repositoryPlaceholders}))
      AND EXISTS (
        SELECT 1 FROM registered_repositories registered
        WHERE registered.repository_url IN (${repositoryPlaceholders})
          AND (
            registered.repository_url = pr.repository_url
            OR registered.repository_url = pr.head_repository_url
          )
      )`;
    const scopeParams = [...repositoryUrls, ...repositoryUrls, ...repositoryUrls];
    const authors = this.handle.connection.all<PullRequestUserDbRow>(
      `${pullRequestUserSelectSql}
      FROM pull_request_users user
      INNER JOIN pull_requests pr ON pr.author_user_id = user.user_id
      WHERE ${scope}
      GROUP BY user.user_id
      ORDER BY user.user_name`,
      scopeParams
    );
    const labels = this.handle.connection.all<{ name: string; color: string | null }>(
      `SELECT label.name, label.color
      FROM pull_request_labels label
      INNER JOIN pull_requests pr ON pr.url = label.pull_request_url
      WHERE ${scope}
      GROUP BY label.name, label.color
      ORDER BY label.name`,
      scopeParams
    );
    const assignees = this.handle.connection.all<PullRequestUserDbRow>(
      `${pullRequestUserSelectSql}
      FROM pull_request_users user
      INNER JOIN pull_request_assignees assignee ON assignee.user_id = user.user_id
      INNER JOIN pull_requests pr ON pr.url = assignee.pull_request_url
      WHERE ${scope}
      GROUP BY user.user_id
      ORDER BY user.user_name`,
      scopeParams
    );
    return { authors, labels, assignees };
  }

  savePullRequest(pr: PullRequest): PullRequest {
    this.handle.transaction(() => {
      if (pr.author) this.upsertUser(pr.author);
      for (const assignee of pr.assignees) this.upsertUser(assignee);
      this.handle.connection.run(
        `INSERT INTO pull_requests (
          url, provider, repository_url, base_ref_name, base_ref_oid,
          head_repository_url, head_ref_name, head_ref_oid, identifier,
          title, description, status, is_draft, author_user_id, additions,
          deletions, changed_files, commit_count, mergeable_status,
          merge_state_status, review_decision, pull_request_created_at,
          pull_request_updated_at
        ) VALUES (${placeholders(23)})
        ON CONFLICT(url) DO UPDATE SET
          provider = excluded.provider,
          repository_url = excluded.repository_url,
          base_ref_name = excluded.base_ref_name,
          base_ref_oid = excluded.base_ref_oid,
          head_repository_url = excluded.head_repository_url,
          head_ref_name = excluded.head_ref_name,
          head_ref_oid = excluded.head_ref_oid,
          identifier = excluded.identifier,
          title = excluded.title,
          description = excluded.description,
          status = excluded.status,
          is_draft = excluded.is_draft,
          author_user_id = excluded.author_user_id,
          additions = excluded.additions,
          deletions = excluded.deletions,
          changed_files = excluded.changed_files,
          commit_count = excluded.commit_count,
          mergeable_status = excluded.mergeable_status,
          merge_state_status = excluded.merge_state_status,
          review_decision = excluded.review_decision,
          pull_request_created_at = excluded.pull_request_created_at,
          pull_request_updated_at = excluded.pull_request_updated_at`,
        [
          pr.url,
          pr.provider,
          pr.repositoryUrl,
          pr.baseRefName,
          pr.baseRefOid,
          pr.headRepositoryUrl,
          pr.headRefName,
          pr.headRefOid,
          pr.identifier,
          pr.title,
          pr.description,
          pr.status,
          pr.isDraft ? 1 : 0,
          pr.author?.userId ?? null,
          pr.additions,
          pr.deletions,
          pr.changedFiles,
          pr.commitCount,
          pr.mergeableStatus,
          pr.mergeStateStatus,
          pr.reviewDecision,
          pr.createdAt,
          pr.updatedAt,
        ]
      );
      this.replaceLabels(pr.url, pr.labels);
      this.replaceAssignees(pr.url, pr.assignees);
    });
    return this.getPullRequestByUrl(pr.url) ?? pr;
  }

  getPullRequestByUrl(url: string): PullRequest | null {
    const row = this.handle.connection.get<PullRequestDbRow>(
      `${pullRequestSelectSql} WHERE url = ?`,
      [url]
    );
    return row ? this.assembleRows([row])[0] : null;
  }

  getPullRequestIdentity(url: string): { repositoryUrl: string; identifier: string | null } | null {
    return (
      this.handle.connection.get<{ repositoryUrl: string; identifier: string | null }>(
        `SELECT repository_url AS repositoryUrl, identifier
        FROM pull_requests WHERE url = ?`,
        [url]
      ) ?? null
    );
  }

  getNewestPullRequestUpdatedAt(repositoryUrl: string): string | null {
    return (
      this.handle.connection.get<{ updatedAt: string | null }>(
        `SELECT MAX(pull_request_updated_at) AS updatedAt
        FROM pull_requests
        WHERE repository_url = ?`,
        [repositoryUrl]
      )?.updatedAt ?? null
    );
  }

  getChecksCommitSha(pullRequestUrl: string): string | null {
    return (
      this.handle.connection.get<{ commitSha: string }>(
        `SELECT commit_sha AS commitSha
        FROM pull_request_checks
        WHERE pull_request_url = ?
        LIMIT 1`,
        [pullRequestUrl]
      )?.commitSha ?? null
    );
  }

  replaceChecks(pullRequestUrl: string, checks: PullRequestCheck[]): void {
    this.handle.transaction(() => {
      this.handle.connection.run('DELETE FROM pull_request_checks WHERE pull_request_url = ?', [
        pullRequestUrl,
      ]);
      for (const check of checks) {
        this.handle.connection.run(
          `INSERT INTO pull_request_checks (
            id, pull_request_url, commit_sha, name, status, conclusion,
            details_url, started_at, completed_at, workflow_name, app_name, app_logo_url
          ) VALUES (${placeholders(12)})`,
          [
            check.id,
            check.pullRequestUrl,
            check.commitSha,
            check.name,
            check.status,
            check.conclusion,
            check.detailsUrl,
            check.startedAt,
            check.completedAt,
            check.workflowName,
            check.appName,
            check.appLogoUrl,
          ]
        );
      }
    });
  }

  clearChecks(pullRequestUrl: string): void {
    this.handle.connection.run('DELETE FROM pull_request_checks WHERE pull_request_url = ?', [
      pullRequestUrl,
    ]);
  }

  replaceComments(pullRequestUrl: string, comments: PullRequestComment[]): void {
    this.handle.transaction(() => {
      for (const comment of comments) {
        if (comment.author) this.upsertUser(comment.author);
      }
      this.handle.connection.run('DELETE FROM pull_request_comments WHERE pull_request_url = ?', [
        pullRequestUrl,
      ]);
      for (const comment of comments) {
        this.handle.connection.run(
          `INSERT INTO pull_request_comments (
            id, pull_request_url, kind, body, url, author_user_id, path, line,
            is_resolved, is_outdated, comment_created_at, comment_updated_at
          ) VALUES (${placeholders(12)})`,
          [
            comment.id,
            pullRequestUrl,
            comment.kind,
            comment.body,
            comment.url,
            comment.author?.userId ?? null,
            comment.path,
            comment.line,
            comment.isResolved ? 1 : 0,
            comment.isOutdated ? 1 : 0,
            comment.createdAt,
            comment.updatedAt,
          ]
        );
      }
    });
  }

  getComments(pullRequestUrl: string): PullRequestComment[] {
    const rows = this.handle.connection.all<PullRequestCommentDbRow>(
      `SELECT
        id,
        pull_request_url AS pullRequestUrl,
        kind,
        body,
        url,
        author_user_id AS authorUserId,
        path,
        line,
        is_resolved AS isResolved,
        is_outdated AS isOutdated,
        comment_created_at AS createdAt,
        comment_updated_at AS updatedAt
      FROM pull_request_comments
      WHERE pull_request_url = ?
      ORDER BY comment_created_at, id`,
      [pullRequestUrl]
    );
    return rows.map((row) => ({
      id: row.id,
      pullRequestUrl: row.pullRequestUrl,
      kind: row.kind,
      body: row.body,
      url: row.url,
      author: row.authorUserId ? this.getUser(row.authorUserId) : null,
      path: row.path,
      line: row.line,
      isResolved: Boolean(row.isResolved),
      isOutdated: Boolean(row.isOutdated),
      createdAt: row.createdAt,
      updatedAt: row.updatedAt,
    }));
  }

  getCommentState(pullRequestUrl: string): PullRequestCommentState | null {
    return (
      this.handle.connection.get<PullRequestCommentState>(
        `SELECT
          etag,
          last_fetched_at AS lastFetchedAt
        FROM pull_request_comment_state
        WHERE pull_request_url = ?`,
        [pullRequestUrl]
      ) ?? null
    );
  }

  setCommentState(pullRequestUrl: string, etag: string | null): void {
    this.handle.connection.run(
      `INSERT INTO pull_request_comment_state (pull_request_url, etag, last_fetched_at)
      VALUES (?, ?, ?)
      ON CONFLICT(pull_request_url) DO UPDATE SET
        etag = excluded.etag,
        last_fetched_at = excluded.last_fetched_at`,
      [pullRequestUrl, etag, Date.now()]
    );
  }

  archiveOldPullRequests(repositoryUrl: string, cutoffIso: string): void {
    this.handle.transaction(() => {
      this.handle.connection.run(
        `DELETE FROM pull_requests
        WHERE repository_url = ?
          AND status IN ('closed', 'merged')
          AND pull_request_updated_at < ?`,
        [repositoryUrl, cutoffIso]
      );
      this.pruneOrphanUsers();
    });
  }

  private requireRegisteredRepository(repositoryUrl: string): RegisteredRepository {
    const repository = this.getRegisteredRepository(repositoryUrl);
    if (!repository) throw new Error(`Repository is not registered: ${repositoryUrl}`);
    return repository;
  }

  private pruneOrphanUsers(): void {
    this.handle.connection.run(
      `DELETE FROM pull_request_users
      WHERE user_id NOT IN (
        SELECT author_user_id FROM pull_requests WHERE author_user_id IS NOT NULL
      )
      AND user_id NOT IN (SELECT user_id FROM pull_request_assignees)
      AND user_id NOT IN (
        SELECT author_user_id FROM pull_request_comments WHERE author_user_id IS NOT NULL
      )`
    );
  }

  private upsertUser(user: PullRequestUser): void {
    this.handle.connection.run(
      `INSERT INTO pull_request_users (
        user_id, user_name, display_name, avatar_url, url, user_updated_at, user_created_at
      ) VALUES (${placeholders(7)})
      ON CONFLICT(user_id) DO UPDATE SET
        user_name = excluded.user_name,
        display_name = excluded.display_name,
        avatar_url = excluded.avatar_url,
        url = excluded.url,
        user_updated_at = excluded.user_updated_at,
        user_created_at = excluded.user_created_at`,
      [
        user.userId,
        user.userName,
        user.displayName,
        user.avatarUrl,
        user.url,
        user.userUpdatedAt,
        user.userCreatedAt,
      ]
    );
  }

  private replaceLabels(pullRequestUrl: string, labels: PullRequestLabel[]): void {
    this.handle.connection.run('DELETE FROM pull_request_labels WHERE pull_request_url = ?', [
      pullRequestUrl,
    ]);
    for (const label of labels) {
      this.handle.connection.run(
        `INSERT INTO pull_request_labels (pull_request_url, name, color) VALUES (?, ?, ?)`,
        [pullRequestUrl, label.name, label.color]
      );
    }
  }

  private replaceAssignees(pullRequestUrl: string, assignees: PullRequestUser[]): void {
    this.handle.connection.run('DELETE FROM pull_request_assignees WHERE pull_request_url = ?', [
      pullRequestUrl,
    ]);
    for (const assignee of assignees) {
      this.handle.connection.run(
        `INSERT INTO pull_request_assignees (pull_request_url, user_id) VALUES (?, ?)`,
        [pullRequestUrl, assignee.userId]
      );
    }
  }

  private assembleRows(rows: PullRequestDbRow[]): PullRequest[] {
    return rows.map((row) => {
      const author = row.authorUserId ? this.getUser(row.authorUserId) : null;
      const labels = this.handle.connection.all<PullRequestLabel>(
        `SELECT name, color FROM pull_request_labels
        WHERE pull_request_url = ? ORDER BY name`,
        [row.url]
      );
      const assignees = this.handle.connection.all<PullRequestUserDbRow>(
        `${pullRequestUserSelectSql}
        FROM pull_request_users user
        INNER JOIN pull_request_assignees assignee ON assignee.user_id = user.user_id
        WHERE assignee.pull_request_url = ?
        ORDER BY user.user_name`,
        [row.url]
      );
      const checks = this.handle.connection.all<PullRequestCheck>(
        `SELECT
          id,
          pull_request_url AS pullRequestUrl,
          commit_sha AS commitSha,
          name,
          status,
          conclusion,
          details_url AS detailsUrl,
          started_at AS startedAt,
          completed_at AS completedAt,
          workflow_name AS workflowName,
          app_name AS appName,
          app_logo_url AS appLogoUrl
        FROM pull_request_checks
        WHERE pull_request_url = ?
        ORDER BY name`,
        [row.url]
      );
      return {
        url: row.url,
        provider: row.provider,
        repositoryUrl: row.repositoryUrl,
        baseRefName: row.baseRefName,
        baseRefOid: row.baseRefOid,
        headRepositoryUrl: row.headRepositoryUrl,
        headRefName: row.headRefName,
        headRefOid: row.headRefOid,
        identifier: row.identifier,
        title: row.title,
        description: row.description,
        status: row.status,
        isDraft: Boolean(row.isDraft),
        additions: row.additions,
        deletions: row.deletions,
        changedFiles: row.changedFiles,
        commitCount: row.commitCount,
        mergeableStatus: row.mergeableStatus,
        mergeStateStatus: row.mergeStateStatus,
        reviewDecision: row.reviewDecision,
        createdAt: row.createdAt,
        updatedAt: row.updatedAt,
        author,
        labels,
        assignees,
        checks,
      };
    });
  }

  private getUser(userId: string): PullRequestUser | null {
    return (
      this.handle.connection.get<PullRequestUserDbRow>(
        `${pullRequestUserSelectSql}
        FROM pull_request_users user
        WHERE user.user_id = ?`,
        [userId]
      ) ?? null
    );
  }
}

const pullRequestSelectSql = `SELECT
  url,
  provider,
  repository_url AS repositoryUrl,
  base_ref_name AS baseRefName,
  base_ref_oid AS baseRefOid,
  head_repository_url AS headRepositoryUrl,
  head_ref_name AS headRefName,
  head_ref_oid AS headRefOid,
  identifier,
  title,
  description,
  status,
  is_draft AS isDraft,
  author_user_id AS authorUserId,
  additions,
  deletions,
  changed_files AS changedFiles,
  commit_count AS commitCount,
  mergeable_status AS mergeableStatus,
  merge_state_status AS mergeStateStatus,
  review_decision AS reviewDecision,
  pull_request_created_at AS createdAt,
  pull_request_updated_at AS updatedAt
FROM pull_requests`;

const pullRequestUserSelectSql = `SELECT
  user.user_id AS userId,
  user.user_name AS userName,
  user.display_name AS displayName,
  user.avatar_url AS avatarUrl,
  user.url,
  user.user_updated_at AS userUpdatedAt,
  user.user_created_at AS userCreatedAt`;

function placeholders(count: number): string {
  return Array.from({ length: count }, () => '?').join(', ');
}

function encodeListCursor(offset: number): string {
  return Buffer.from(JSON.stringify({ offset }), 'utf8').toString('base64url');
}

function decodeListCursor(cursor: string | null): number {
  if (!cursor) return 0;
  try {
    const parsed = JSON.parse(Buffer.from(cursor, 'base64url').toString('utf8')) as {
      offset?: unknown;
    };
    if (!Number.isSafeInteger(parsed.offset) || Number(parsed.offset) < 0) {
      throw new Error('Invalid offset');
    }
    return Number(parsed.offset);
  } catch {
    throw new Error('Invalid pull request list cursor');
  }
}
