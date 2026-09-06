import {
  index,
  integer,
  primaryKey,
  sqliteTable,
  text,
  uniqueIndex,
} from 'drizzle-orm/sqlite-core';

// Identity is intentionally absent (spec: github-git-settings §8): registration
// only records *what* to sync; *as whom* is resolved by the desktop per sync.
export const registeredRepositories = sqliteTable(
  'registered_repositories',
  {
    id: text('id').primaryKey(),
    repositoryUrl: text('repository_url').notNull(),
    createdAt: integer('created_at').notNull(),
    updatedAt: integer('updated_at').notNull(),
  },
  (table) => ({
    repositoryUrlIdx: uniqueIndex('idx_registered_repositories_url').on(table.repositoryUrl),
  })
);

export const syncCursors = sqliteTable(
  'sync_cursors',
  {
    repositoryId: text('repository_id')
      .notNull()
      .references(() => registeredRepositories.id, { onDelete: 'cascade' }),
    kind: text('kind').notNull().$type<'full' | 'incremental'>(),
    lastUpdatedAt: text('last_updated_at').notNull(),
    pageCursor: text('page_cursor'),
    done: integer('done', { mode: 'boolean' }).notNull(),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.repositoryId, table.kind] }),
  })
);

export const pullRequestUsers = sqliteTable('pull_request_users', {
  userId: text('user_id').primaryKey(),
  userName: text('user_name').notNull(),
  displayName: text('display_name'),
  avatarUrl: text('avatar_url'),
  url: text('url'),
  userUpdatedAt: text('user_updated_at'),
  userCreatedAt: text('user_created_at'),
});

export const pullRequests = sqliteTable(
  'pull_requests',
  {
    url: text('url').primaryKey(),
    provider: text('provider').notNull().default('github'),
    repositoryUrl: text('repository_url').notNull(),
    baseRefName: text('base_ref_name').notNull(),
    baseRefOid: text('base_ref_oid').notNull(),
    headRepositoryUrl: text('head_repository_url').notNull(),
    headRefName: text('head_ref_name').notNull(),
    headRefOid: text('head_ref_oid').notNull(),
    identifier: text('identifier'),
    title: text('title').notNull(),
    description: text('description'),
    status: text('status').notNull().default('open'),
    isDraft: integer('is_draft', { mode: 'boolean' }).notNull().default(false),
    authorUserId: text('author_user_id').references(() => pullRequestUsers.userId, {
      onDelete: 'set null',
    }),
    additions: integer('additions'),
    deletions: integer('deletions'),
    changedFiles: integer('changed_files'),
    commitCount: integer('commit_count'),
    mergeableStatus: text('mergeable_status'),
    mergeStateStatus: text('merge_state_status'),
    reviewDecision: text('review_decision'),
    pullRequestCreatedAt: text('pull_request_created_at').notNull(),
    pullRequestUpdatedAt: text('pull_request_updated_at').notNull(),
  },
  (table) => ({
    repositoryUrlIdx: index('idx_pull_requests_repository_url').on(table.repositoryUrl),
    headRepositoryUrlIdx: index('idx_pull_requests_head_repository_url').on(
      table.headRepositoryUrl
    ),
    headRefNameIdx: index('idx_pull_requests_head_ref_name').on(table.headRefName),
    updatedAtIdx: index('idx_pull_requests_updated_at').on(table.pullRequestUpdatedAt),
  })
);

export const pullRequestLabels = sqliteTable(
  'pull_request_labels',
  {
    pullRequestUrl: text('pull_request_url')
      .notNull()
      .references(() => pullRequests.url, { onDelete: 'cascade' }),
    name: text('name').notNull(),
    color: text('color'),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.pullRequestUrl, table.name] }),
    nameIdx: index('idx_pull_request_labels_name').on(table.name),
  })
);

export const pullRequestAssignees = sqliteTable(
  'pull_request_assignees',
  {
    pullRequestUrl: text('pull_request_url')
      .notNull()
      .references(() => pullRequests.url, { onDelete: 'cascade' }),
    userId: text('user_id')
      .notNull()
      .references(() => pullRequestUsers.userId, { onDelete: 'cascade' }),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.pullRequestUrl, table.userId] }),
    pullRequestUrlIdx: index('idx_pull_request_assignees_pr_url').on(table.pullRequestUrl),
    userIdIdx: index('idx_pull_request_assignees_user_id').on(table.userId),
  })
);

export const pullRequestChecks = sqliteTable(
  'pull_request_checks',
  {
    id: text('id').primaryKey(),
    pullRequestUrl: text('pull_request_url')
      .notNull()
      .references(() => pullRequests.url, { onDelete: 'cascade' }),
    commitSha: text('commit_sha').notNull(),
    name: text('name').notNull(),
    status: text('status').notNull(),
    conclusion: text('conclusion'),
    detailsUrl: text('details_url'),
    startedAt: text('started_at'),
    completedAt: text('completed_at'),
    workflowName: text('workflow_name'),
    appName: text('app_name'),
    appLogoUrl: text('app_logo_url'),
  },
  (table) => ({
    pullRequestUrlIdx: index('idx_pull_request_checks_pr_url').on(table.pullRequestUrl),
  })
);

export const pullRequestComments = sqliteTable(
  'pull_request_comments',
  {
    id: text('id').primaryKey(),
    pullRequestUrl: text('pull_request_url')
      .notNull()
      .references(() => pullRequests.url, { onDelete: 'cascade' }),
    kind: text('kind').notNull().$type<'issue' | 'review'>(),
    body: text('body').notNull(),
    url: text('url').notNull(),
    authorUserId: text('author_user_id').references(() => pullRequestUsers.userId, {
      onDelete: 'set null',
    }),
    path: text('path'),
    line: integer('line'),
    isResolved: integer('is_resolved', { mode: 'boolean' }).notNull(),
    isOutdated: integer('is_outdated', { mode: 'boolean' }).notNull(),
    commentCreatedAt: text('comment_created_at').notNull(),
    commentUpdatedAt: text('comment_updated_at').notNull(),
  },
  (table) => ({
    pullRequestUrlIdx: index('idx_pull_request_comments_pr_url').on(table.pullRequestUrl),
  })
);

export const pullRequestCommentState = sqliteTable('pull_request_comment_state', {
  pullRequestUrl: text('pull_request_url')
    .primaryKey()
    .references(() => pullRequests.url, { onDelete: 'cascade' }),
  etag: text('etag'),
  lastFetchedAt: integer('last_fetched_at').notNull(),
});

export type RegisteredRepositoryRow = typeof registeredRepositories.$inferSelect;
export type SyncCursorRow = typeof syncCursors.$inferSelect;
export type PullRequestRow = typeof pullRequests.$inferSelect;
export type PullRequestUserRow = typeof pullRequestUsers.$inferSelect;
export type PullRequestLabelRow = typeof pullRequestLabels.$inferSelect;
export type PullRequestCheckRow = typeof pullRequestChecks.$inferSelect;
export type PullRequestCommentRow = typeof pullRequestComments.$inferSelect;
export type PullRequestCommentStateRow = typeof pullRequestCommentState.$inferSelect;
