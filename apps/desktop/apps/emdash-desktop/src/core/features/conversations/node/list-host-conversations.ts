import { and, eq, isNull } from 'drizzle-orm';
import { conversationRegistryTable as conversations } from '@core/features/conversations/api/node/registry';
import type {
  HostConversationRow,
  HostConversationScope,
} from '@core/primitives/conversations/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { projects, tasks } from '@core/services/app-db/node/schema';

/**
 * The machine page's discovery and cleanup read (spec §8): every cached conversation
 * observation of one host — task-linked and orphaned alike. Live rows carrying a
 * deletion tombstone surface as removal-pending (ADR 0006): the visible pending state
 * until the reconcile sweep converges and the sync delivery purges the row.
 */
export async function listHostConversations(
  db: AppDb,
  scope: HostConversationScope
): Promise<HostConversationRow[]> {
  const hostIdentity =
    scope.sshConnectionId === null
      ? isNull(conversations.sshConnectionId)
      : eq(conversations.sshConnectionId, scope.sshConnectionId);

  const rows = db
    .select({
      conversation: conversations,
      projectName: projects.name,
      taskName: tasks.name,
    })
    .from(conversations)
    .leftJoin(projects, eq(conversations.projectId, projects.id))
    .leftJoin(tasks, eq(conversations.taskId, tasks.id))
    .where(and(eq(conversations.location, scope.location), hostIdentity))
    .all();

  const result: HostConversationRow[] = [];
  for (const { conversation, projectName, taskName } of rows) {
    // Untracked rows are settled removals (or forget-host leftovers awaiting purge) —
    // not part of the host's conversations surface.
    if (conversation.untrackedAt !== null) continue;
    result.push({
      id: conversation.id,
      title: conversation.title,
      provider: conversation.provider,
      type: conversation.type,
      projectId: conversation.projectId,
      taskId: conversation.taskId,
      projectName: projectName ?? null,
      taskName: taskName ?? null,
      workspacePath: conversation.workspacePath,
      lastSessionActivityAt: conversation.lastSessionActivityAt,
      observedStatus: conversation.observedStatus,
      lastObservedAt: conversation.lastObservedAt,
      createdAt: conversation.createdAt,
      updatedAt: conversation.updatedAt,
      pendingRemoval: conversation.deletionTombstone !== null,
    });
  }
  return result;
}
