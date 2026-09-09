import { and, eq } from 'drizzle-orm';
import { conversationRegistryTable as conversations } from '@core/features/conversations/api/node/registry';
import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import type { AppDb } from '@core/services/app-db/node/db';
import { launchTuiConversation } from './launch-tui-conversation';

export async function hydrateConversation(
  db: AppDb,
  taskSessions: Pick<TaskSessionManager, 'getTask'>,
  projectId: string,
  taskId: string,
  conversationId: string,
  telemetry: Pick<TelemetryService, 'capture'>,
  initialSize?: { cols: number; rows: number }
): Promise<void> {
  const [row] = await db
    .select()
    .from(conversations)
    .where(
      and(
        eq(conversations.id, conversationId),
        eq(conversations.projectId, projectId),
        eq(conversations.taskId, taskId)
      )
    )
    .limit(1);
  if (!row) throw new Error('Conversation not found');

  if (row.type === 'acp') {
    return;
  }

  await launchTuiConversation({
    projectId,
    taskId,
    conversationId,
    initialSize,
    telemetry,
    database: db,
    taskSessions,
  });
}
