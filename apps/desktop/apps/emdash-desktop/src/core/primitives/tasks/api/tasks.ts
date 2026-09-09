import type { RuntimeResolveError } from '@emdash/core/primitives/runtime-resolution/api';
import z from 'zod';
import type { AutomationRunStatus } from '@core/primitives/automations/api/automation-run-status';
import type { Conversation } from '@core/primitives/conversations/api';
import type {
  CreateBranchError,
  FetchPrForReviewError,
  GitBranchRef,
  PushError,
} from '@core/primitives/git/api';
import type { LinkedIssue } from '@core/primitives/linked-issues/api';
import type { TaskConfig } from '@core/primitives/tasks/api';
import type { WorkspaceConfig } from '@core/primitives/workspaces/api';
import type { PullRequest } from '@root/src/core/services/pull-requests/api';

// ---------------------------------------------------------------------------
// Workspace intent types — stored on the task row as JSON in `workspace_intent`
// ---------------------------------------------------------------------------

/**
 * Describes the git operations to perform when setting up a workspace.
 * Stored in `tasks.workspace_intent` as part of a `WorkspaceIntent` JSON blob.
 */
export type GitSetup =
  | { kind: 'none' }
  | { kind: 'use-branch'; branchName: string }
  | { kind: 'create-branch'; branchName: string; fromBranch: GitBranchRef; pushBranch?: boolean }
  | {
      kind: 'pr-branch';
      prNumber: number;
      headBranch: string;
      headRepositoryUrl: string;
      isFork: boolean;
      /** When set, a new branch is created on top of the PR head for the task. */
      taskBranch?: string;
      pushBranch?: boolean;
    };

export const taskLifecycleStatuses = z.enum([
  'todo',
  'in_progress',
  'review',
  'done',
  'cancelled',
  'backlog',
  'duplicate',
  'triage',
]);

export type TaskLifecycleStatus = z.infer<typeof taskLifecycleStatuses>;
export type LifecycleScriptType = 'setup' | 'run' | 'teardown';

export type AutomationRunMeta = {
  automationName: string;
  status: AutomationRunStatus;
  scheduledAt: number | null;
  startedAt: number | null;
  finishedAt: number | null;
};

export type Task = {
  id: string;
  projectId: string;
  name: string;
  status: TaskLifecycleStatus;
  createdAt: string;
  updatedAt: string;
  /** ISO timestamp: when lifecycle status last changed (current status entered). */
  statusChangedAt: string;
  archivedAt?: string;
  lastInteractedAt?: string;
  linkedIssue?: LinkedIssue;
  isPinned: boolean;
  prs: PullRequest[];
  conversations: Record<string, number>;
  workspaceGit?: { linesAdded: number; linesDeleted: number };
  workspaceId?: string;
  type: 'task' | 'automation-run';
  automationRunId?: string;
  automationRunMeta?: AutomationRunMeta;
};

export type TaskRow = Omit<Task, 'prs' | 'workspaceGit'>;

export type TaskActiveWorkspace = {
  workspaceId: string;
  path: string;
  sshConnectionId?: string;
};

export type TaskListRow = TaskRow & {
  /** Desktop-owned active-session metadata; does not require current Host attachment. */
  activeWorkspace?: TaskActiveWorkspace;
};

export type TaskListData = {
  tasks: TaskListRow[];
};

/** One workspace lifecycle step (host registry contract): machine facts only. */
export type WorkspaceLifecycleStepInfo = {
  id:
    | 'adopt-worktree'
    | 'fetch-branch'
    | 'fetch-remote-base'
    | 'create-worktree'
    | 'configure-branch'
    | 'copy-artifacts'
    | 'push-branch'
    | 'fetch-refs'
    | 'prepare'
    | 'setup'
    | 'run'
    | 'teardown';
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped' | 'cancelled';
  startedAt: number | null;
  finishedAt: number | null;
  message?: string;
  params: Record<string, string | number | boolean>;
};

/**
 * Raw observed git facts (mirror observedGit v2) that PR association and
 * checkout-drift derive from desktop-side. Null means not-yet-observed — old
 * hosts and v1 payloads — which degrades association to branch matching only
 * and drift to unknown.
 */
export type WorkspaceObservedPrFacts = {
  branch: string | null;
  /** Raw `branch.<b>.emdash-pr-url` config value (a canonical PR URL). */
  prBreadcrumb: string | null;
  /** Verbatim `branch.<b>.merge` plus the upstream remote's resolved URL. */
  upstream: { mergeRef: string; remoteUrl: string | null } | null;
  /** Full OID of the observed HEAD; null on unborn HEAD or probe failure. */
  headOid: string | null;
  /** Commits ahead of / behind `@{u}`; null when the tracking ref doesn't resolve. */
  ahead: number | null;
  behind: number | null;
};

export type TaskStatsData = {
  /** Latest Host observation represented in this snapshot; null means never observed. */
  observedAt?: number | null;
  byWorkspaceId: Record<string, { linesAdded: number; linesDeleted: number }>;
  workspaceById?: Record<
    string,
    {
      path: string | null;
      observedAt?: number | null;
      observedStatus: 'present' | 'missing' | null;
      /** In-flight createWorktree stage from the host runtime overlay. */
      creation: { stage: string; startedAt: number } | null;
      /** Durable outcome of the last createWorktree run for this record. */
      lastCreateOutcome: {
        status: 'started' | 'succeeded' | 'failed';
        stage?: string;
        message?: string;
      } | null;
      /** Lifecycle steps in canonical order (creation, background, and script steps). */
      lifecycle?: WorkspaceLifecycleStepInfo[] | null;
      /** Observed PR-association facts; null while the host has not observed v2 yet. */
      observedPr?: WorkspaceObservedPrFacts | null;
    }
  >;
};

export type TaskBootstrapStatus =
  | { status: 'ready' }
  | { status: 'bootstrapping' }
  | { status: 'error'; message: string }
  | { status: 'not-started' };

export type CreateTaskParams = {
  id: string;
  projectId: string;
  /** Typed, versioned task configuration (name, issue link, conversation, status). */
  taskConfig: TaskConfig;
  /** Typed, versioned workspace configuration (git setup + workspace location). */
  workspaceConfig: WorkspaceConfig;
};

export type CreateTaskError =
  | { type: 'project-not-found' }
  | { type: 'project-unavailable'; reason: string; message: string }
  | { type: 'initial-commit-required'; branch: string }
  | { type: 'branch-create-failed'; branch: string; error: CreateBranchError }
  | { type: 'pr-fetch-failed'; error: FetchPrForReviewError; remote: string }
  | { type: 'branch-not-found'; branch: string }
  | { type: 'worktree-setup-failed'; branch: string; message?: string }
  | { type: 'provision-failed'; message: string }
  | { type: 'provision-timeout'; timeoutMs: number; step?: string }
  | { type: 'workspace-unavailable'; workspaceId: string; message: string }
  /** Creation admission refusal (ADR 0006): the target carries a pending deletion tombstone. */
  | { type: 'workspace-tombstone-pending'; workspaceId: string; message: string };

export type CreateTaskWarning = {
  type: 'branch-publish-failed';
  branch: string;
  remote: string;
  error: PushError;
};

export type CreateTaskSuccess = {
  task: Task;
  initialConversation?: Conversation;
  warning?: CreateTaskWarning;
};

export type RenameTaskError = { type: 'task-not-found'; taskId: string };

export type RenameTaskSuccess = {
  task: Task;
};

export type ProvisionTaskResult = {
  path: string;
  workspaceId: string;
};

export type ProvisionWorkspaceError =
  | { type: 'no-intent' }
  | { type: 'missing-workspace' }
  | { type: 'project-missing'; projectId: string }
  | { type: 'project-unavailable'; reason: string; message: string }
  | { type: 'cancelled'; message?: string }
  | { type: 'setup-failed'; stepKind: string; stepErrorType: string; message?: string }
  | RuntimeResolveError;

export type DeleteTaskOptions = {
  deleteWorktree?: boolean;
  deleteBranch?: boolean;
  /** Default-on cascade: delete the task's conversation records on their host. */
  deleteConversations?: boolean;
};

export type TaskDeletePreflightItem = {
  taskId: string;
  /** taskBranch exists and no sibling task shares it */
  hasWorktree: boolean;
  /** dirty per the mirror's host-synced git observation */
  hasUncommittedChanges: boolean;
  /** hasWorktree && taskBranch differs from sourceBranch */
  hasDeletableBranch: boolean;
  /** Mirror diff stats; untracked files' lines count as additions. */
  changedLines?: { added: number; deleted: number } | null;
  /** Commits ahead of upstream per the mirror observation. */
  unpushedCommits?: number | null;
  /** Epoch-ms stamp of the host observation the stakes were read from. */
  observedAt?: number | null;
  /** False disables artifact deletion in the dialog — nothing is queued offline. */
  hostReachable: boolean;
};

export type DeletePreflightResult = {
  tasks: TaskDeletePreflightItem[];
};
