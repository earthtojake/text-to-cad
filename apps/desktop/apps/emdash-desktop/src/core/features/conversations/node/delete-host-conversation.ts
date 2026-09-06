import { conversationEvents } from '@core/features/conversations/api/node/conversation-events';
import type { ConversationRemovalBroker } from '@core/features/conversations/api/node/operations/conversation-removal';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { removeConversationOrTombstone } from './remove-conversation';

/**
 * The machine page's per-record delete (spec §8): the same removal verb as task-scoped
 * deletion, but link-free — orphaned and task-linked records alike are deletable from
 * the discovery surface by id alone. Reachable hosts remove in the foreground; an
 * unreachable host gets a durable deletion tombstone swept on reconnect (ADR 0006).
 */
export async function deleteHostConversation(
  db: AppDb,
  runtimes: ConversationRemovalBroker,
  conversationId: string,
  telemetry: Pick<TelemetryService, 'capture'>
): Promise<void> {
  const row = createConversationRegistry(db).getLive(conversationId);
  // Idempotent toward the caller: an absent row is a no-op.
  if (!row) return;

  await removeConversationOrTombstone(db, runtimes, row);

  conversationEvents._emit('conversation:deleted', conversationId);
  appDbPokes.conversations.poke({
    projectId: row.projectId ?? undefined,
    taskId: row.taskId ?? undefined,
  });
  telemetry.capture('conversation_deleted', { conversation_id: conversationId });
}
