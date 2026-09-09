import { conversationEvents } from '@core/features/conversations/api/node/conversation-events';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import { MAX_CONVERSATION_TITLE_LENGTH } from '@core/primitives/conversations/api';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { conversationWireEvents } from './event-host';
import type { HostConversationMutationDeps } from './host-mutation';
import { resolveConversationHostClient } from './host-mutation';

/**
 * Renames a conversation through its host index (spec §4.3): a foreground wire mutation,
 * last-write-wins at the sole-writer index. The local cache is only updated with the
 * host-acknowledged value from the response — no local dirty state; offline renames are
 * refused like offline creation.
 */
export async function renameConversation(
  deps: HostConversationMutationDeps,
  conversationId: string,
  name: string
) {
  const title = name.trim().slice(0, MAX_CONVERSATION_TITLE_LENGTH);
  const { row, client } = await resolveConversationHostClient(deps, conversationId);

  const renamed = await client.rename({ conversationId, title });
  if (!renamed.success) {
    throw new Error(`Rename was rejected by the host: ${renamed.error.message}`);
  }

  const now = new Date().toISOString();
  createConversationRegistry(deps.db).refresh(conversationId, {
    title: renamed.data.title,
    updatedAt: new Date(renamed.data.updatedAt).toISOString(),
    lastObservedAt: now,
  });

  if (row.projectId !== null && row.taskId !== null) {
    conversationEvents._emit(
      'conversation:renamed',
      conversationId,
      row.projectId,
      row.taskId,
      renamed.data.title
    );
    conversationWireEvents.emit(undefined, {
      type: 'changed',
      conversationId,
      taskId: row.taskId,
      projectId: row.projectId,
      changes: { title: renamed.data.title },
    });
  }
  appDbPokes.conversations.poke({
    projectId: row.projectId ?? undefined,
    taskId: row.taskId ?? undefined,
  });
}
