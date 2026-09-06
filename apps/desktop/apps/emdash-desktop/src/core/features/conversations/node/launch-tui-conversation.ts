import { KeyedMutex } from '@emdash/shared/concurrency';
import { and, eq } from 'drizzle-orm';
import { conversationRegistryTable as conversations } from '@core/features/conversations/api/node/registry';
import type { EnsureConversationSessionOutcome } from '@core/features/conversations/api/node/types';
import { mapConversationRowToConversation } from '@core/features/conversations/api/node/utils';
import { resolveTask } from '@core/features/projects/api/node/utils';
import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import type { Conversation } from '@core/primitives/conversations/api';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import type { AppDb } from '@core/services/app-db/node/db';

type LaunchTuiConversationDb = Pick<AppDb, 'select' | 'update'>;

export type LaunchTuiConversationInput = {
  projectId: string;
  taskId: string;
  conversationId: string;
  initialSize?: { cols: number; rows: number };
  database: LaunchTuiConversationDb;
  telemetry: Pick<TelemetryService, 'capture'>;
  taskSessions: Pick<TaskSessionManager, 'getTask'>;
};

export type LaunchTuiConversationResult = {
  conversation: Conversation;
  outcome: EnsureConversationSessionOutcome;
};

const launchMutex = new KeyedMutex();

export async function launchTuiConversation({
  projectId,
  taskId,
  conversationId,
  initialSize,
  database,
  telemetry,
  taskSessions,
}: LaunchTuiConversationInput): Promise<LaunchTuiConversationResult> {
  return launchMutex.runExclusive(conversationId, async () => {
    const [row] = await database
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
    const conversation = mapConversationRowToConversation(row);
    if (conversation === null) throw new Error('Conversation has no task link');
    if (row.type === 'acp') {
      return { conversation, outcome: 'attached' };
    }

    const task = resolveTask(taskSessions, projectId, taskId);
    if (!task) throw new Error('Task not found');

    const isFirstSpawn = row.providerSessionId === null;
    const initialPrompt =
      isFirstSpawn && row.config?.type === 'pty' ? row.config.initialPrompt : undefined;

    const launched = await task.conversations.ensureSession({
      conversation,
      mode: isFirstSpawn ? 'start' : 'resume',
      initialSize,
      initialPrompt,
    });

    if (launched.outcome !== 'attached') {
      telemetry.capture('agent_run_started', {
        provider: conversation.providerId,
        project_id: conversation.projectId,
        task_id: conversation.taskId,
        conversation_id: conversation.id,
      });
    }

    // The resume handle is host truth now: the TUI runtime reports the emdash-chosen
    // handle (or a hook-captured native id) into the index at spawn, and convergence
    // flows it into `providerSessionId` here — no client placeholder write (spec §3.3).
    return { conversation, outcome: launched.outcome };
  });
}
