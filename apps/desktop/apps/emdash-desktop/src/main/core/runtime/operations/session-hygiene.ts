import type { SessionIntentStore } from '@emdash/core/services/session-intents/api';
import type { Logger } from '@emdash/shared/logger';
import { eq } from 'drizzle-orm';
import type { AppDb } from '@core/services/app-db/node/db';
import { conversations, projects, tasks } from '@core/services/app-db/node/schema';

export type SessionHygieneDependencies = {
  agentStatus: { resetToIdle(params: { conversationId: string }): Promise<void> };
  createSessionIntentStores(): { acp: SessionIntentStore; tuiAgents: SessionIntentStore };
  logger: Pick<Logger, 'warn'>;
};

/**
 * Desktop-plane session hygiene, the remnant of the dissolved cleanup-sessions
 * operation: agent status badges for dead conversations reset to idle and
 * stale session intents are pruned. Killing orphaned host sessions is the
 * workspace host's session GC job, not the desktop's.
 */
export async function sweepSessionHygiene(
  db: AppDb,
  dependencies: SessionHygieneDependencies
): Promise<void> {
  const owners = await db
    .select({
      conversationId: conversations.id,
      taskDeletedAt: tasks.deletedAt,
      projectDeletedAt: projects.deletedAt,
    })
    .from(conversations)
    .innerJoin(tasks, eq(tasks.id, conversations.taskId))
    .innerJoin(projects, eq(projects.id, tasks.projectId));
  const validConversationIds = new Set(
    owners
      .filter((owner) => owner.taskDeletedAt === null && owner.projectDeletedAt === null)
      .map((owner) => owner.conversationId)
  );

  for (const owner of owners) {
    if (validConversationIds.has(owner.conversationId)) continue;
    try {
      await dependencies.agentStatus.resetToIdle({ conversationId: owner.conversationId });
    } catch (error) {
      dependencies.logger.warn('session hygiene could not reset agent status', {
        conversationId: owner.conversationId,
        error: String(error),
      });
    }
  }

  const intentStores = dependencies.createSessionIntentStores();
  for (const store of [intentStores.acp, intentStores.tuiAgents]) {
    const result = await store.list();
    if (!result.success) {
      dependencies.logger.warn('session hygiene could not read session intents', {
        error: result.error.message,
      });
      continue;
    }
    for (const intent of result.data) {
      if (validConversationIds.has(intent.conversationId)) continue;
      const removed = await store.remove(intent.conversationId);
      if (!removed.success) {
        dependencies.logger.warn('session hygiene could not prune session intent', {
          conversationId: intent.conversationId,
          error: removed.error.message,
        });
      }
    }
  }
}
