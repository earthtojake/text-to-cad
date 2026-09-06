import { and, eq } from 'drizzle-orm';
import {
  conversationRegistryTable as conversations,
  liveConversations,
} from '@core/features/conversations/api/node/registry';
import { mapConversationRowsToConversations } from '@core/features/conversations/api/node/utils';
import type { AppDb } from '@core/services/app-db/node/db';

export async function getConversationsForTask(db: AppDb, projectId: string, taskId: string) {
  const rows = await db
    .select()
    .from(conversations)
    .where(
      and(
        eq(conversations.projectId, projectId),
        eq(conversations.taskId, taskId),
        liveConversations()
      )
    );
  return mapConversationRowsToConversations(rows);
}
