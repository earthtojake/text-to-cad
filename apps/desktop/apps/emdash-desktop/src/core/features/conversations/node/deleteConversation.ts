import { and, eq } from 'drizzle-orm';
import { conversationEvents } from '@core/features/conversations/api/node/conversation-events';
import type { ConversationRemovalBroker } from '@core/features/conversations/api/node/operations/conversation-removal';
import {
  conversationRegistryTable as conversations,
  liveConversations,
} from '@core/features/conversations/api/node/registry';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { removeConversationOrTombstone } from './remove-conversation';

/**
 * User-initiated conversation deletion, task-scoped (conversation spec §4.3 as amended
 * for the reconcile sweep): a reachable host removes in the foreground — killing any
 * live session is part of the verb, then the index row deletes — and an unreachable
 * host gets a durable deletion tombstone swept on reconnect (ADR 0006).
 */
export async function deleteConversation(
  db: AppDb,
  runtimes: ConversationRemovalBroker,
  projectId: string,
  taskId: string,
  conversationId: string,
  telemetry: Pick<TelemetryService, 'capture'>
): Promise<void> {
  const [convRow] = await db
    .select({
      id: conversations.id,
      location: conversations.location,
      sshConnectionId: conversations.sshConnectionId,
    })
    .from(conversations)
    .where(
      and(
        eq(conversations.id, conversationId),
        eq(conversations.projectId, projectId),
        eq(conversations.taskId, taskId),
        liveConversations()
      )
    )
    .limit(1);
  // Idempotent toward the caller: an already-deleted row is a no-op.
  if (!convRow) return;

  await removeConversationOrTombstone(db, runtimes, convRow);

  conversationEvents._emit('conversation:deleted', conversationId);
  appDbPokes.conversations.poke({ projectId, taskId });
  telemetry.capture('conversation_deleted', {
    project_id: projectId,
    task_id: taskId,
    conversation_id: conversationId,
  });
}
