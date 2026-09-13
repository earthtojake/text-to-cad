import { sshConnectionIdOf, type HostRef } from '@emdash/core/primitives/host/api';
import type { HostAbsolutePath } from '@emdash/core/primitives/path/api';
import { err, ok, type Result } from '@emdash/shared';
import { and, eq, isNull, ne } from 'drizzle-orm';
import { tombstoneConversationForRemoval } from '@core/features/conversations/api/node/operations/conversation-removal';
import {
  createConversationRegistry,
  conversationRegistryTable as conversationRows,
  liveConversations,
} from '@core/features/conversations/api/node/registry';
import { projectIsBeingDeleted } from '@core/features/projects/api/node/project-deletion';
import {
  killTaskSessions,
  type TaskSessionCleanup,
} from '@core/features/tasks/api/node/task-session-cleanup';
import { taskSubject } from '@core/features/tasks/contributions/subject';
import { operationHostRef } from '@core/features/workspaces/api/node/operation-host-ref';
import {
  deleteWorkspaceThroughRegistry,
  type WorkspaceRemovalBroker,
} from '@core/features/workspaces/api/node/operations/workspace-removal';
import {
  createWorkspaceRegistry,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import type { MutationError } from '@core/primitives/wire/api/mutations';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import {
  projects,
  tasks,
  type ConversationRow,
  type TaskRow,
} from '@core/services/app-db/node/schema';
import { reconcileSweepTriggers } from '@core/services/reconcile-sweep/node/reconcile-sweep-triggers';
import type { MementosRuntimeClient } from '@core/services/runtime-broker/api/clients';

/**
 * Task deletion as plain desktop code (operation-log retirement spec §3, §7): the
 * desktop-local stages — session kill, conversation cascade, row purge — complete
 * immediately in one transaction and never block on a host. The host-artifact half
 * rides the workspace removal verbs: a reachable host removes the worktree now, while
 * a mid-call disconnect leaves the workspace row unchanged for an explicit retry.
 * Nothing submits to the operations kernel.
 */

export type DeleteTaskInput = {
  taskId: string;
  deleteWorktree?: boolean;
  deleteBranch?: boolean;
  /**
   * Explicit, declinable, default-on cascade (spec §7.2): mark the task's conversation
   * records with their own deletion tombstones, converged by the conversations
   * reconcile-sweep kind. Declining unlinks the records instead — they orphan into the
   * discovery surface.
   */
  deleteConversations?: boolean;
};

export type TaskDeletionResult = Result<void, MutationError>;

export type TaskDeletionDependencies = {
  db: AppDb;
  runtimes: WorkspaceRemovalBroker;
  sessionCleanup: TaskSessionCleanup;
  getMementosRuntimeClient(): Promise<MementosRuntimeClient>;
  telemetry: Pick<TelemetryService, 'capture'>;
  unregisterFileSearchRoot(path: HostAbsolutePath, host: HostRef): Promise<void> | void;
};

export async function deleteTask(
  dependencies: TaskDeletionDependencies,
  input: DeleteTaskInput
): Promise<TaskDeletionResult> {
  const { db } = dependencies;
  const createdAt = Date.now();
  const deleteConversations = input.deleteConversations !== false;

  const [task] = await db
    .select()
    .from(tasks)
    .where(and(eq(tasks.id, input.taskId), isNull(tasks.deletedAt)))
    .limit(1);
  if (!task) {
    return err({ type: 'task-not-found', message: `Task ${input.taskId} was not found` });
  }
  if (projectIsBeingDeleted(db, task.projectId)) {
    return err({ type: 'project-deleting', message: 'Project is being deleted.' });
  }
  const workspace = task.workspaceId
    ? createWorkspaceRegistry(db).getLive(task.workspaceId)
    : undefined;
  const [project] = await db
    .select({
      repositoryLocation: workspaces.location,
      repositorySshConnectionId: workspaces.sshConnectionId,
    })
    .from(projects)
    .leftJoin(workspaces, eq(workspaces.id, projects.repositoryWorkspaceId))
    .where(eq(projects.id, task.projectId))
    .limit(1);
  // Shared-workspace guard: another live task on the row means unlink only — no
  // host removal.
  const otherTaskRows = task.workspaceId
    ? await db
        .select({ id: tasks.id })
        .from(tasks)
        .where(
          and(
            eq(tasks.workspaceId, task.workspaceId),
            ne(tasks.id, task.id),
            isNull(tasks.deletedAt)
          )
        )
        .limit(1)
    : [];
  const workspaceShared = otherTaskRows.length > 0;
  const taskConversations = await db
    .select()
    .from(conversationRows)
    .where(and(eq(conversationRows.taskId, task.id), liveConversations()));
  const host = operationHostRef({
    workspace,
    repository: project && {
      location: project.repositoryLocation,
      sshConnectionId: project.repositorySshConnectionId,
    },
  });

  await killTaskSessions(dependencies, task, host, workspace?.path ?? undefined);
  const tombstonedConversations = purgeTaskDesktopRows(db, task, taskConversations, {
    deleteConversations,
    createdAt,
  });
  appDbPokes.tasks.poke({ projectId: task.projectId, taskId: task.id });
  appDbPokes.conversations.poke({ projectId: task.projectId, taskId: task.id });
  // Tombstoned-while-reachable trigger (ADR 0006): freshly written conversation
  // tombstones converge now when the host is up; otherwise the reconnect sweep owns them.
  if (tombstonedConversations > 0) reconcileSweepTriggers.poke(host);

  // Artifact destruction is a capability derived from durable provenance, never from
  // the caller's boolean alone. Directory/repository workspaces and scanner-adopted
  // worktrees detach with the task; Emdash did not create an artifact it may destroy.
  const canDeleteOwnedWorktree = workspace?.kind === 'worktree' && workspace.config !== null;
  // The host-artifact half, after the desktop rows committed: the verb call is
  // fail-fast and best-effort here — a failure leaves the workspace row live for a
  // later explicit removal from the workspaces surface.
  if (
    task.workspaceId &&
    !workspaceShared &&
    canDeleteOwnedWorktree &&
    input.deleteWorktree !== false
  ) {
    await deleteWorkspaceThroughRegistry(db, dependencies.runtimes, task.workspaceId, {
      deleteBranch: input.deleteBranch ?? false,
    });
    if (workspace?.path && workspaceIsUntracked(db, workspace.id)) {
      const removed = hostFileRefFromNativePath(workspace.path, sshConnectionIdOf(host));
      await dependencies.unregisterFileSearchRoot(removed.path, removed.host);
    }
  }

  await purgeTaskLocalState(dependencies, task);
  return ok(undefined);
}

/**
 * The desktop-local stage: conversation cascade plus the task-row delete, one
 * transaction. Accepted cascade tombstones each live record — the rows stay live and
 * visible as the pending state, unlinked by the task-row FK — and the conversations
 * sweep converges them. Declined cascade is an annotation delete: the records orphan
 * into the discovery surface. Returns how many tombstones were written.
 */
function purgeTaskDesktopRows(
  db: AppDb,
  task: TaskRow,
  taskConversations: readonly ConversationRow[],
  options: { deleteConversations: boolean; createdAt: number }
): number {
  const conversationRegistry = createConversationRegistry(db);
  let tombstoned = 0;
  db.transaction((tx) => {
    if (options.deleteConversations) {
      for (const row of taskConversations) {
        const { outcome } = tombstoneConversationForRemoval(tx, {
          conversationId: row.id,
          createdAt: options.createdAt,
        });
        if (outcome === 'tombstoned') tombstoned += 1;
      }
    } else {
      for (const row of taskConversations) {
        conversationRegistry.annotate(
          row.id,
          { taskId: null, projectId: null, isInitialConversation: false },
          tx
        );
      }
    }
    tx.delete(tasks).where(eq(tasks.id, task.id)).run();
  });
  return tombstoned;
}

export async function purgeTaskLocalState(
  dependencies: Pick<TaskDeletionDependencies, 'getMementosRuntimeClient' | 'telemetry'>,
  task: Pick<TaskRow, 'id' | 'projectId'>
): Promise<void> {
  const client = await dependencies.getMementosRuntimeClient();
  const result = await client.deleteBySubject(taskSubject({ taskId: task.id }));
  if (!result.success) throw new Error(result.error.message);
  dependencies.telemetry.capture('task_deleted', {
    project_id: task.projectId ?? undefined,
    task_id: task.id,
  });
}

function workspaceIsUntracked(db: AppDb, workspaceId: string): boolean {
  const row = db
    .select({ untrackedAt: workspaces.untrackedAt })
    .from(workspaces)
    .where(eq(workspaces.id, workspaceId))
    .limit(1)
    .get();
  return row !== undefined && row.untrackedAt !== null;
}
