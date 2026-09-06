import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { type AgentStatus } from '@core/primitives/agents/api';
import {
  type Conversation,
  type ConversationType,
  type InitialQueuePrompt,
} from '@core/primitives/conversations/api';
import { type ConversationRow } from '@core/services/app-db/node/schema';

function initialQueueFromRow(row: ConversationRow): InitialQueuePrompt[] | undefined {
  if (row.providerSessionId !== null) return undefined;
  const config = row.config;
  if (config?.type !== 'acp') return undefined;
  if (config.initialQueue?.length) return config.initialQueue;
  const legacyPrompt = config.initialPrompt?.trim();
  return legacyPrompt ? [{ text: legacyPrompt }] : undefined;
}

/**
 * Maps a registry row to the task-surface Conversation DTO. Unlinked rows (adopted mirror
 * rows with no task annotation) map to null: they never appear inside task surfaces
 * (spec §5.4) — they surface on the machine page instead.
 */
export function mapConversationRowToConversation(row: ConversationRow): Conversation | null {
  if (row.taskId === null || row.projectId === null) return null;
  const config = row.config;
  return {
    id: row.id,
    title: row.title,
    taskId: row.taskId,
    projectId: row.projectId,
    providerId: row.provider as AgentProviderId,
    autoApprove: config?.autoApprove,
    sessionId: row.providerSessionId ?? undefined,
    model: config?.model,
    contextKey: config?.type === 'acp' ? config.contextKey : undefined,
    modeId: config?.type === 'acp' ? config.modeId : undefined,
    initialQueue: initialQueueFromRow(row),
    lastInteractedAt: row.lastSessionActivityAt ?? null,
    isInitialConversation: row.isInitialConversation,
    agentStatus: (row.agentStatus as AgentStatus | null) ?? null,
    agentStatusSeen: row.agentStatusSeen === 1,
    type: (row.type as ConversationType | null) ?? 'pty',
  };
}

/** List-mapping helper: maps rows and drops unlinked mirror rows. */
export function mapConversationRowsToConversations(rows: ConversationRow[]): Conversation[] {
  return rows
    .map(mapConversationRowToConversation)
    .filter((conversation): conversation is Conversation => conversation !== null);
}
