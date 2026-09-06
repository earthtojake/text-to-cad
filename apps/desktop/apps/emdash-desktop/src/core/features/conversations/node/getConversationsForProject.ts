import { and, eq } from 'drizzle-orm';
import {
  conversationRegistryTable as conversations,
  liveConversations,
} from '@core/features/conversations/api/node/registry';
import { mapConversationRowsToConversations } from '@core/features/conversations/api/node/utils';
import type { AppDb } from '@core/services/app-db/node/db';

export async function getConversationsForProject(db: AppDb, projectId: string) {
  const rows = await db
    .select()
    .from(conversations)
    .where(and(eq(conversations.projectId, projectId), liveConversations()));
  return mapConversationRowsToConversations(rows);
}
