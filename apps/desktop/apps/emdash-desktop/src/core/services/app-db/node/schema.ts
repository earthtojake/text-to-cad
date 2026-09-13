import type { TerminalShellId } from '@emdash/core/primitives/terminal-shell/api';
import { sql } from 'drizzle-orm';
import {
  index,
  integer,
  primaryKey,
  sqliteTable,
  text,
  uniqueIndex,
} from 'drizzle-orm/sqlite-core';
import type { AutomationRunStatus } from '@core/primitives/automations/api/automation-run-status';
import {
  automationConversationConfig,
  automationTriggerConfig,
  storedAutomationTaskConfig,
} from '@core/primitives/automations/api/config';
import {
  conversationConfig,
  conversationDeletionTombstone,
} from '@core/primitives/conversations/api';
import { linkedIssue } from '@core/primitives/linked-issues/api';
import { providerAccountMeta } from '@core/primitives/provider-accounts/api';
import { sshConnectionMetadata } from '@core/primitives/ssh/api';
import { workspaceConfig } from '@core/primitives/workspaces/api';
import {
  workspaceCreateOutcome,
  workspaceDeletionTombstone,
  workspaceObservedGit,
  workspaceRemovalAttempt,
  workspaceRuntimeOverlay,
  workspaceScriptOutcomes,
} from '@core/primitives/workspaces/api';
import type { WorkspaceKind } from '@core/primitives/workspaces/api';
import { notificationPayload } from '@root/src/core/services/notifications/api';
import type { StoredBranch } from './stored-branch';
import { versionedJsonColumn } from './versioned-column';

export const sshConnections = sqliteTable(
  'ssh_connections',
  {
    id: text('id').primaryKey(),
    name: text('name').notNull(),
    host: text('host').notNull(),
    port: integer('port').notNull().default(22),
    username: text('username').notNull(),
    authType: text('auth_type').notNull().default('agent'), // 'password' | 'key' | 'agent'
    privateKeyPath: text('private_key_path'), // optional, for key auth
    useAgent: integer('use_agent').notNull().default(0), // boolean, 0=false, 1=true
    metadata: versionedJsonColumn(sshConnectionMetadata)('metadata'),
    shouldConnect: integer('should_connect'), // nullable tri-state: null=auto, 0=off, 1=on
    createdAt: text('created_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text('updated_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => ({
    nameIdx: uniqueIndex('idx_ssh_connections_name').on(table.name),
    hostIdx: index('idx_ssh_connections_host').on(table.host),
  })
);

export const projects = sqliteTable(
  'projects',
  {
    id: text('id').primaryKey(),
    name: text('name').notNull(),
    baseRef: text('base_ref'),
    /**
     * The shared workspace representing this project's repository root. Set at
     * creation; the repository row carries the project's path and host identity.
     */
    repositoryWorkspaceId: text('repository_workspace_id'),
    createdAt: text('created_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text('updated_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    deletedAt: text('deleted_at'),
  },
  (table) => ({
    repositoryWorkspaceIdIdx: uniqueIndex('idx_projects_repository_workspace_id')
      .on(table.repositoryWorkspaceId)
      .where(sql`${table.repositoryWorkspaceId} IS NOT NULL AND ${table.deletedAt} IS NULL`),
  })
);

export const projectRemotes = sqliteTable(
  'project_remotes',
  {
    projectId: text('project_id')
      .notNull()
      .references(() => projects.id, { onDelete: 'cascade' }),
    remoteName: text('remote_name').notNull(),
    remoteUrl: text('remote_url').notNull(),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.projectId, table.remoteName] }),
  })
);

export const projectSettings = sqliteTable('project_settings', {
  projectId: text('project_id')
    .primaryKey()
    .references(() => projects.id, { onDelete: 'cascade' }),
  baseProjectSettingsJson: text('base_project_settings_json').notNull().default('{}'),
  shareableProjectSettingsJson: text('shareable_project_settings_json').notNull().default('{}'),
  legacyConfigMigratedAt: text('legacy_config_migrated_at'),
  createdAt: text('created_at')
    .notNull()
    .default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text('updated_at')
    .notNull()
    .default(sql`CURRENT_TIMESTAMP`),
});

export const appSettings = sqliteTable(
  'app_settings',
  {
    key: text('key').primaryKey(),
    value: text('value').notNull(),
    updatedAt: integer('updated_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => ({
    keyIdx: uniqueIndex('idx_app_settings_key').on(table.key),
  })
);

export const notifications = sqliteTable(
  'notifications',
  {
    id: text('id').primaryKey(),
    kind: text('kind').notNull(),
    groupKey: text('group_key').notNull(),
    title: text('title').notNull(),
    body: text('body').notNull(),
    payload: versionedJsonColumn(notificationPayload)('payload').notNull(),
    count: integer('count').notNull().default(1),
    createdAt: integer('created_at').notNull(),
    readAt: integer('read_at'),
  },
  (table) => ({
    createdAtIdx: index('idx_notifications_created_at').on(table.createdAt),
    groupKeyIdx: index('idx_notifications_group_key').on(table.groupKey),
    readAtIdx: index('idx_notifications_read_at').on(table.readAt),
  })
);

export const tasks = sqliteTable(
  'tasks',
  {
    id: text('id').primaryKey(),
    projectId: text('project_id')
      .notNull()
      .references(() => projects.id, { onDelete: 'cascade' }),
    name: text('name').notNull(),
    status: text('status').notNull(),
    sourceBranch: text('source_branch').$type<StoredBranch>(), // @deprecated — moved to workspaces.config (git.fromBranch)
    taskBranch: text('task_branch'), // @deprecated — use workspaces.config for provisioned branch identity
    linkedIssue: versionedJsonColumn(linkedIssue)('linked_issue'),
    archivedAt: text('archived_at'), // null = active, timestamp = archived
    createdAt: text('created_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text('updated_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    lastInteractedAt: text('last_interacted_at'),
    statusChangedAt: text('status_changed_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    isPinned: integer('is_pinned').notNull().default(0), // boolean, 0=false, 1=true
    workspaceId: text('workspace_id'),
    type: text('type').notNull().default('task'), // 'task' | 'automation-run'
    automationRunId: text('automation_run_id'), // set when type = 'automation-run'; runtime-owned reference, intentionally no FK
    deletedAt: text('deleted_at'),
  },
  (table) => ({
    projectIdIdx: index('idx_tasks_project_id').on(table.projectId),
    activeAutomationRunIdIdx: uniqueIndex('idx_tasks_active_automation_run_id')
      .on(table.automationRunId)
      .where(sql`${table.automationRunId} IS NOT NULL AND ${table.deletedAt} IS NULL`),
  })
);

export const workspaces = sqliteTable(
  'workspaces',
  {
    id: text('id').primaryKey(),
    type: text('type').notNull().$type<'local' | 'project-ssh'>(), // @deprecated — use kind + location
    /** Describes the nature of the workspace: a git worktree, a repository root, or a directory. */
    kind: text('kind').$type<WorkspaceKind>(),
    /** Where the workspace runs: on the local machine or over SSH. */
    location: text('location').$type<'local' | 'remote'>(),
    /** FK to ssh_connections; only set when location = 'remote'. */
    sshConnectionId: text('ssh_connection_id').references(() => sshConnections.id, {
      onDelete: 'set null',
    }),
    /** Parent repository registry row for git worktrees. */
    parentId: text('parent_id'),
    path: text('path'),
    /** The rich-provenance annotation (client-owned); adopted rows have none. */
    config: versionedJsonColumn(workspaceConfig)('config'),
    /** How the row entered the host registry: explicit registration or host adoption. */
    origin: text('origin').$type<'registered' | 'adopted'>(),
    observedStatus: text('observed_status').$type<'present' | 'missing'>(),
    // Host registry observations (ADR 0005): refreshed wholesale on every `records`
    // delivery. Timestamps are epoch-ms as delivered.
    observedGit: versionedJsonColumn(workspaceObservedGit)('observed_git'),
    lastCreateOutcome: versionedJsonColumn(workspaceCreateOutcome)('last_create_outcome'),
    /** Last failed removal attempt (ADR 0006); null while no delete has failed. */
    lastRemovalAttempt: versionedJsonColumn(workspaceRemovalAttempt)('last_removal_attempt'),
    /** Durable per-script (prepare/setup/run) last outcomes; survive daemon restarts. */
    scriptOutcomes: versionedJsonColumn(workspaceScriptOutcomes)('script_outcomes'),
    /** Persisted overlay for one renderer read path; a daemon-restart delivery clears it. */
    runtimeOverlay: versionedJsonColumn(workspaceRuntimeOverlay)('runtime_overlay'),
    lastActivatedAt: integer('last_activated_at'),
    /** Epoch-ms host observation stamp for the registry sync path. */
    observedAt: integer('observed_at'),
    /**
     * Durable deletion intent (ADR 0006): frozen options + the target record UUID,
     * written atomically at delete time against an unreachable host. Null = no pending
     * deletion. The row stays live (visible) until the reconcile sweep converges.
     */
    deletionTombstone: versionedJsonColumn(workspaceDeletionTombstone)('deletion_tombstone'),
    createdAt: text('created_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text('updated_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    untrackedAt: text('untracked_at'),
  },
  (table) => ({
    localPathIdx: uniqueIndex('idx_workspaces_local_path')
      .on(table.path)
      .where(
        sql`${table.location} = 'local' AND ${table.untrackedAt} IS NULL AND ${table.path} IS NOT NULL`
      ),
    remotePathIdx: uniqueIndex('idx_workspaces_remote_path')
      .on(table.sshConnectionId, table.path)
      .where(
        sql`${table.location} = 'remote' AND ${table.untrackedAt} IS NULL AND ${table.path} IS NOT NULL`
      ),
    parentIdIdx: index('idx_workspaces_parent_id').on(table.parentId),
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

    identifier: text('identifier'), // #123 for github
    title: text('title').notNull(),
    description: text('description'),
    status: text('status').notNull().default('open'),
    isDraft: integer('is_draft'),

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

    pullRequestCreatedAt: text('pull_request_created_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    pullRequestUpdatedAt: text('pull_request_updated_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => ({
    urlIdx: uniqueIndex('idx_pull_requests_url').on(table.url),
    repositoryUrlIdx: index('idx_pull_requests_repository_url').on(table.repositoryUrl),
    headRepositoryUrlIdx: index('idx_pull_requests_head_repository_url').on(
      table.headRepositoryUrl
    ),
  })
);

export const pullRequestLabels = sqliteTable(
  'pull_request_labels',
  {
    pullRequestId: text('pull_request_id')
      .notNull()
      .references(() => pullRequests.url, { onDelete: 'cascade' }),
    name: text('name').notNull(),
    color: text('color'),
  },
  (table) => ({
    pk: primaryKey({ columns: [table.pullRequestId, table.name] }),
    nameIdx: index('idx_prl_name').on(table.name),
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
    pullRequestUrlIdx: index('idx_pra_pull_request_url').on(table.pullRequestUrl),
    userIdIdx: index('idx_pra_user_id').on(table.userId),
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
    conclusion: text('conclusion').notNull(),

    detailsUrl: text('details_url'),
    startedAt: text('started_at'),
    completedAt: text('completed_at'),
    workflowName: text('workflow_name'),
    appName: text('app_name'),
    appLogoUrl: text('app_logo_url'),
  },
  (table) => ({
    pullRequestUrlIdx: index('idx_prc_pull_request_url').on(table.pullRequestUrl),
  })
);

export const automations = sqliteTable(
  'automations',
  {
    id: text('id').primaryKey(),
    name: text('name').notNull(),
    projectId: text('project_id').references(() => projects.id, {
      onDelete: 'set null',
    }),
    triggerConfig: versionedJsonColumn(automationTriggerConfig)('trigger_config'),
    conversationConfig: versionedJsonColumn(automationConversationConfig)('conversation_config'),
    taskConfig: versionedJsonColumn(storedAutomationTaskConfig)('task_config'),
    enabled: integer('enabled').notNull().default(1),
    revision: integer('revision').notNull().default(1),
    createdAt: integer('created_at').notNull(),
    updatedAt: integer('updated_at').notNull(),
    deletedAt: integer('deleted_at'),
  },
  (table) => ({
    projectIdIdx: index('idx_automations_project_id').on(table.projectId),
  })
);

export const automationRuns = sqliteTable(
  'automation_runs',
  {
    id: text('id').primaryKey(),
    automationId: text('automation_id').notNull(),
    automationName: text('automation_name').notNull(),
    status: text('status').$type<AutomationRunStatus>().notNull(),
    scheduledAt: integer('scheduled_at'),
    startedAt: integer('started_at'),
    finishedAt: integer('finished_at'),
    seq: integer('seq').notNull().default(0),
  },
  (table) => ({
    automationIdIdx: index('idx_automation_runs_automation_id').on(table.automationId),
  })
);

/**
 * The conversation registry (spec §5): a per-host mirror of host conversation records plus
 * client-owned annotations, keyed by the emdash conversation id the host record carries.
 * All writes go through the ConversationRegistry sole-writer module.
 */
export const conversations = sqliteTable(
  'conversations',
  {
    id: text('id').primaryKey(),
    // Annotations (client-owned, never in host payloads). Links are nullable: an adopted
    // mirror row has none. The task cascade is retired (spec §10.5): task deletion unlinks
    // — records only leave the registry through explicit, declinable delete requests
    // (conv.explicit-delete).
    projectId: text('project_id').references(() => projects.id, { onDelete: 'cascade' }),
    taskId: text('task_id').references(() => tasks.id, { onDelete: 'set null' }),
    isInitialConversation: integer('is_initial_conversation', {
      mode: 'boolean',
    }),
    agentStatusSeen: integer('agent_status_seen').default(1),
    /** Device-local cache converging from the live session model — outside the observation discipline. */
    agentStatus: text('agent_status'),
    // Observations (cached host record fields, host-owned).
    title: text('title').notNull(),
    provider: text('provider'),
    type: text('type'),
    config: versionedJsonColumn(conversationConfig)('config'),
    createdAt: text('created_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text('updated_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    /** Frozen working directory of the host record. */
    cwd: text('cwd'),
    /** Observed workspace association (path value, not a FK; may dangle). */
    workspacePath: text('workspace_path'),
    /** Last-observed provider resume handle — a pointer, never the record's identity. */
    providerSessionId: text('provider_session_id'),
    idRegime: text('id_regime').$type<'emdash-chosen' | 'provider-minted' | 'none'>(),
    lastSessionActivityAt: text('last_session_activity_at'),
    observedStatus: text('observed_status').$type<'present' | 'missing'>(),
    lastObservedAt: text('last_observed_at'),
    // Registry bookkeeping (spec §5.1).
    /** How the row entered the registry — bookkeeping only, never missing-sweep input. */
    origin: text('origin').$type<'registered' | 'adopted'>().notNull().default('registered'),
    /** Source host identity; refreshable (last-observed host wins on duplicated ids). */
    location: text('location').$type<'local' | 'remote'>(),
    sshConnectionId: text('ssh_connection_id').references(() => sshConnections.id, {
      onDelete: 'set null',
    }),
    /**
     * Durable deletion intent (ADR 0006): the target record UUID + write stamp,
     * written atomically at delete time against an unreachable host. Null = no pending
     * deletion. The row stays live (visible) until the reconcile sweep converges.
     */
    deletionTombstone: versionedJsonColumn(conversationDeletionTombstone)('deletion_tombstone'),
    untrackedAt: text('untracked_at'),
  },
  (table) => ({
    taskIdIdx: index('idx_conversations_task_id').on(table.taskId),
  })
);

export const terminals = sqliteTable(
  'terminals',
  {
    id: text('id').primaryKey(),
    projectId: text('project_id')
      .notNull()
      .references(() => projects.id, { onDelete: 'cascade' }),
    taskId: text('task_id')
      .notNull()
      .references(() => tasks.id, { onDelete: 'cascade' }),
    ssh: integer('ssh').notNull().default(0), // boolean, 0=false, 1=true
    name: text('name').notNull(),
    shellId: text('shell_id').$type<TerminalShellId>().notNull().default('system'),
    createdAt: text('created_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
    updatedAt: text('updated_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => ({
    taskIdIdx: index('idx_terminals_task_id').on(table.taskId),
  })
);

export const kv = sqliteTable(
  'kv',
  {
    key: text('key').primaryKey(),
    value: text('value').notNull(),
    updatedAt: integer('updated_at')
      .notNull()
      .default(sql`CURRENT_TIMESTAMP`),
  },
  (table) => ({
    keyIdx: uniqueIndex('idx_kv_key').on(table.key),
  })
);

export const providerAccounts = sqliteTable(
  'provider_accounts',
  {
    id: text('id').primaryKey(),
    providerId: text('provider_id').notNull(),
    accountId: text('account_id').notNull(),
    credentialRef: text('credential_ref').notNull(),
    isDefault: integer('is_default', { mode: 'boolean' }).notNull().default(false),
    meta: versionedJsonColumn(providerAccountMeta)('meta'),
    createdAt: integer('created_at').notNull(),
    updatedAt: integer('updated_at').notNull(),
  },
  (table) => ({
    accountIdx: uniqueIndex('idx_provider_accounts_provider_account').on(
      table.providerId,
      table.accountId
    ),
    defaultIdx: uniqueIndex('idx_provider_accounts_default')
      .on(table.providerId)
      .where(sql`is_default = 1`),
  })
);

export const appSecrets = sqliteTable(
  'app_secrets',
  {
    key: text('key').primaryKey(),
    secret: text('secret').notNull(),
  },
  (table) => ({
    keyIdx: uniqueIndex('idx_app_secrets_key').on(table.key),
  })
);

export type SshConnectionRow = typeof sshConnections.$inferSelect;
export type SshConnectionInsert = typeof sshConnections.$inferInsert;
export type ProjectRow = typeof projects.$inferSelect;
export type AutomationRow = typeof automations.$inferSelect;
export type AutomationRunRow = typeof automationRuns.$inferSelect;
export type ProjectSettingsRow = typeof projectSettings.$inferSelect;
export type ProjectSettingsInsert = typeof projectSettings.$inferInsert;
export type TaskRow = typeof tasks.$inferSelect;
export type ConversationRow = typeof conversations.$inferSelect;
export type ConversationInsert = typeof conversations.$inferInsert;
export type TerminalRow = typeof terminals.$inferSelect;
export type KvRow = typeof kv.$inferSelect;
export type KvInsert = typeof kv.$inferInsert;
export type AppSecretRow = typeof appSecrets.$inferSelect;
export type AppSecretInsert = typeof appSecrets.$inferInsert;
export type ProviderAccountRow = typeof providerAccounts.$inferSelect;
export type ProviderAccountInsert = typeof providerAccounts.$inferInsert;
export type WorkspaceRow = typeof workspaces.$inferSelect;
export type WorkspaceInsert = typeof workspaces.$inferInsert;
