import {
  formatHostRef,
  type HostRef,
  type SerializedHostRef,
} from '@emdash/core/primitives/host/api';
import type { AppDb } from '@core/services/app-db/node/db';
import type { TaskRow } from '@core/services/app-db/node/schema';

/**
 * The session-kill half of task deletion (operation-log retirement spec §3), shared
 * with the project-delete cascade. Best effort by design: an unreachable host must not
 * block desktop deletion — the host reaps orphaned sessions when the worktree is
 * removed.
 */

export type TaskSessionTargets = {
  acpConversationIds: string[];
  tuiConversationIds: string[];
  terminalSessionIds: string[];
  tmuxSessionNames: string[];
};

export type TaskSessionScope = {
  taskId: string;
  projectId: string;
  hostRef: SerializedHostRef;
};

export type TaskSessionContext = { workspacePath?: string };

/** Structural slice of the desktop session-cleanup helpers; tests fake it directly. */
export type TaskSessionCleanup = {
  resolve(
    db: AppDb,
    scope: TaskSessionScope,
    context: TaskSessionContext
  ): Promise<TaskSessionTargets>;
  killAcp(db: AppDb, scope: TaskSessionScope, targets: TaskSessionTargets): Promise<void>;
  killTerminals(
    db: AppDb,
    scope: TaskSessionScope,
    context: TaskSessionContext,
    targets: TaskSessionTargets
  ): Promise<void>;
};

export async function killTaskSessions(
  dependencies: { db: AppDb; sessionCleanup: TaskSessionCleanup },
  task: Pick<TaskRow, 'id' | 'projectId'>,
  host: HostRef,
  workspacePath: string | undefined
): Promise<void> {
  const { db, sessionCleanup } = dependencies;
  const scope: TaskSessionScope = {
    taskId: task.id,
    projectId: task.projectId,
    hostRef: formatHostRef(host),
  };
  const context: TaskSessionContext = { workspacePath };
  try {
    const targets = await sessionCleanup.resolve(db, scope, context);
    if (targets.acpConversationIds.length > 0) {
      await sessionCleanup.killAcp(db, scope, targets);
    }
    if (
      targets.tuiConversationIds.length > 0 ||
      targets.terminalSessionIds.length > 0 ||
      targets.tmuxSessionNames.length > 0
    ) {
      await sessionCleanup.killTerminals(db, scope, context, targets);
    }
  } catch {
    // Swallowed by design; see module comment.
  }
}
