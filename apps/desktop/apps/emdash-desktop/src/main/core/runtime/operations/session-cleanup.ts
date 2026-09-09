import {
  parseHostRef,
  sshConnectionIdOf,
  type SerializedHostRef,
} from '@emdash/core/primitives/host/api';
import { makeTmuxSessionName } from '@emdash/core/services/pty/api';
import { and, eq, inArray, isNull, ne, or } from 'drizzle-orm';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { makePtySessionId } from '@core/primitives/pty/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { conversations, terminals, type WorkspaceRow } from '@core/services/app-db/node/schema';
import type {
  AcpRuntimeClient,
  TerminalsRuntimeClient,
  TuiAgentsRuntimeClient,
} from '@main/gateway/desktop-workers';

export type LifecycleSessionTargets = {
  acpConversationIds: string[];
  tuiConversationIds: string[];
  terminalSessionIds: string[];
  tmuxSessionNames: string[];
};

/** The task being deleted plus the host its sessions live on — all this module needs. */
export type LifecycleSessionScope = {
  taskId?: string | null;
  projectId?: string | null;
  hostRef: SerializedHostRef;
};

export type LifecycleSessionContext = {
  workspace?: Pick<WorkspaceRow, 'id'>;
  workspacePath?: string;
};

export type SessionCleanupDependencies = {
  getAcpRuntimeClient(): Promise<AcpRuntimeClient>;
  getProjectTerminals(
    projectId: string
  ): Pick<TerminalsRuntimeClient, 'killTmuxSessions'> | undefined;
  getTerminalsRuntimeClient(): Promise<TerminalsRuntimeClient>;
  getTuiAgentsRuntimeClient(): Promise<TuiAgentsRuntimeClient>;
};

type SessionTargetSets = {
  [K in keyof LifecycleSessionTargets]: Set<string>;
};

/**
 * Resolves the task-scoped sessions a task deletion should stop.
 * Path-scoped session cleanup is the workspace host's job (the removeWorktree
 * verb kills sessions under the worktree path).
 */
export async function resolveLifecycleSessionTargets(
  _dependencies: SessionCleanupDependencies,
  db: AppDb,
  operation: LifecycleSessionScope,
  _context: LifecycleSessionContext
): Promise<LifecycleSessionTargets> {
  const targets: SessionTargetSets = {
    acpConversationIds: new Set(),
    tuiConversationIds: new Set(),
    terminalSessionIds: new Set(),
    tmuxSessionNames: new Set(),
  };
  const taskIds = operation.taskId ? [operation.taskId] : [];
  if (taskIds.length > 0) {
    const [acpRows, tuiRows, terminalRows] = await Promise.all([
      db
        .select({
          id: conversations.id,
          taskId: conversations.taskId,
          projectId: conversations.projectId,
        })
        .from(conversations)
        .where(and(inArray(conversations.taskId, taskIds), eq(conversations.type, 'acp'))),
      db
        .select({
          id: conversations.id,
          taskId: conversations.taskId,
          projectId: conversations.projectId,
        })
        .from(conversations)
        .where(
          and(
            inArray(conversations.taskId, taskIds),
            or(ne(conversations.type, 'acp'), isNull(conversations.type))
          )
        ),
      db
        .select({ id: terminals.id, taskId: terminals.taskId, projectId: terminals.projectId })
        .from(terminals)
        .where(inArray(terminals.taskId, taskIds)),
    ]);

    for (const row of acpRows) targets.acpConversationIds.add(row.id);
    for (const row of tuiRows) targets.tuiConversationIds.add(row.id);
    for (const row of terminalRows) {
      targets.terminalSessionIds.add(makePtySessionId(row.projectId, row.taskId, row.id));
    }
    for (const row of [...acpRows, ...tuiRows, ...terminalRows]) {
      if (row.projectId === null || row.taskId === null) continue;
      targets.tmuxSessionNames.add(
        makeTmuxSessionName(makePtySessionId(row.projectId, row.taskId, row.id))
      );
    }
  }

  return toArrays(targets);
}

export async function killLifecycleAcpSessions(
  dependencies: SessionCleanupDependencies,
  _db: AppDb,
  _operation: LifecycleSessionScope,
  targets: LifecycleSessionTargets
): Promise<void> {
  if (targets.acpConversationIds.length === 0) return;
  const client = await dependencies.getAcpRuntimeClient();
  for (const conversationId of targets.acpConversationIds) {
    const result = await client.kill({ conversationId });
    if (!result.success && !isMissingError(result.error)) {
      throw new Error(errorMessage(result.error));
    }
  }
}

export async function killLifecycleTerminalSessions(
  dependencies: SessionCleanupDependencies,
  _db: AppDb,
  operation: LifecycleSessionScope,
  context: LifecycleSessionContext,
  targets: LifecycleSessionTargets
): Promise<void> {
  if (targets.tuiConversationIds.length > 0) {
    const tui = await dependencies.getTuiAgentsRuntimeClient();
    for (const conversationId of targets.tuiConversationIds) {
      const result = await tui.delete({ conversationId });
      if (!result.success && !isMissingError(result.error)) {
        throw new Error(errorMessage(result.error));
      }
    }
  }

  if (context.workspacePath) {
    const terminalClient = await dependencies.getTerminalsRuntimeClient();
    const workspace = hostFileRefFromNativePath(
      context.workspacePath,
      sshConnectionIdOf(parseHostRef(operation.hostRef))
    );
    for (const sessionId of targets.terminalSessionIds) {
      const result = await terminalClient.kill({ key: { workspace, id: sessionId } });
      if (!result.success && !isMissingError(result.error)) {
        throw new Error(errorMessage(result.error));
      }
    }
  }

  if (!operation.projectId || targets.tmuxSessionNames.length === 0) return;
  const projectTerminals = dependencies.getProjectTerminals(operation.projectId);
  if (!projectTerminals) return;
  await projectTerminals.killTmuxSessions({ sessionNames: targets.tmuxSessionNames });
}

function toArrays(targets: SessionTargetSets): LifecycleSessionTargets {
  return {
    acpConversationIds: [...targets.acpConversationIds],
    tuiConversationIds: [...targets.tuiConversationIds],
    terminalSessionIds: [...targets.terminalSessionIds],
    tmuxSessionNames: [...targets.tmuxSessionNames],
  };
}

function isMissingError(error: unknown): boolean {
  if (typeof error !== 'object' || error === null || !('type' in error)) return false;
  const type = String(error.type);
  return type === 'not-found' || type === 'workspace-not-found' || type === 'missing-workspace';
}

function errorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'message' in error) {
    return String(error.message);
  }
  return String(error);
}
