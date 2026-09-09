import { and, eq, isNull } from 'drizzle-orm';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { tasks } from '@core/services/app-db/node/schema';

/**
 * The machine page's "link into a task" affordance (spec §8): task links are client
 * registry annotations, so linking never touches the host record — it only rewrites
 * the row's `projectId`/`taskId` annotation columns.
 */
export async function linkConversationToTask(
  db: AppDb,
  input: { conversationId: string; projectId: string; taskId: string }
): Promise<void> {
  const registry = createConversationRegistry(db);
  const row = registry.getLive(input.conversationId);
  if (!row) {
    throw new Error(`Conversation ${input.conversationId} was not found`);
  }

  const [task] = db
    .select({ id: tasks.id })
    .from(tasks)
    .where(
      and(eq(tasks.id, input.taskId), eq(tasks.projectId, input.projectId), isNull(tasks.deletedAt))
    )
    .limit(1)
    .all();
  if (!task) {
    throw new Error(`Task ${input.taskId} was not found in project ${input.projectId}`);
  }

  registry.annotate(input.conversationId, {
    projectId: input.projectId,
    taskId: input.taskId,
  });

  appDbPokes.conversations.poke({ projectId: input.projectId, taskId: input.taskId });
  if (row.projectId && row.projectId !== input.projectId) {
    appDbPokes.conversations.poke({
      projectId: row.projectId,
      taskId: row.taskId ?? undefined,
    });
  }
}
