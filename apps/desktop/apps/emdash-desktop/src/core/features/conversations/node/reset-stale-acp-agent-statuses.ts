import { log } from '@emdash/shared/logger';
import { and, eq, inArray } from 'drizzle-orm';
import { conversationRegistryTable as conversations } from '@core/features/conversations/api/node/registry';
import type { AppDb } from '@core/services/app-db/node/db';

export async function resetStaleAcpAgentStatuses(db: AppDb): Promise<void> {
  try {
    await db
      .update(conversations)
      .set({ agentStatus: 'idle', agentStatusSeen: 1 })
      .where(
        and(
          eq(conversations.type, 'acp'),
          eq(conversations.location, 'local'),
          inArray(conversations.agentStatus, ['working', 'awaiting-input'])
        )
      );
  } catch (error) {
    log.warn('Failed to reset stale ACP agent statuses', { error: String(error) });
  }
}
