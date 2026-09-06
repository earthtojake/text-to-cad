import { and, eq } from 'drizzle-orm';
import { conversationRegistryTable as conversations } from '@core/features/conversations/api/node/registry';
import { resolveTask } from '@core/features/projects/api/node/utils';
import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import type { AppDb } from '@core/services/app-db/node/db';

export async function dehydrateConversation(
  db: AppDb,
  taskSessions: Pick<TaskSessionManager, 'getTask'>,
  projectId: string,
  taskId: string,
  conversationId: string
): Promise<void> {
  const [row] = await db
    .select({ type: conversations.type })
    .from(conversations)
    .where(
      and(
        eq(conversations.id, conversationId),
        eq(conversations.projectId, projectId),
        eq(conversations.taskId, taskId)
      )
    )
    .limit(1);

  if (row?.type === 'acp') {
    return;
  }

  const task = resolveTask(taskSessions, projectId, taskId);
  await task?.conversations.detachSession(conversationId);
}
