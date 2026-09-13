import { err, ok, type BaseError, type Result } from '@emdash/shared';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import type { ConversationConfig } from '@core/primitives/conversations/api';
import type { HostConversationMutationDeps } from './host-mutation';
import { resolveConversationHostClient } from './host-mutation';

export type SetModeIdError = BaseError<
  'empty-mode-id' | 'conversation-not-found' | 'not-acp-conversation' | 'host-rejected'
>;

/**
 * Persists the last user-selected ACP session mode id into the conversation's config so
 * it can be re-applied on the next session start/resume. Config is host-resident and
 * client-editable (spec §3.2), so the write is a foreground `updateConfig` wire mutation;
 * the local cache only holds the host-acknowledged config from the response.
 *
 * Mode ids only exist for ACP conversations, so non-ACP configs are rejected.
 * Returns the conversation routing context for callers that need to emit an update.
 */
export async function setConversationModeId(
  deps: HostConversationMutationDeps,
  conversationId: string,
  modeId: string
): Promise<Result<{ projectId: string | null; taskId: string | null }, SetModeIdError>> {
  const trimmed = modeId.trim();
  if (!trimmed) return err({ type: 'empty-mode-id' });

  let resolved: Awaited<ReturnType<typeof resolveConversationHostClient>>;
  try {
    resolved = await resolveConversationHostClient(deps, conversationId);
  } catch (error) {
    return err({
      type: 'conversation-not-found',
      message: error instanceof Error ? error.message : conversationId,
    });
  }
  const { row, client } = resolved;
  if (row.config?.type !== 'acp') {
    return err({ type: 'not-acp-conversation', message: conversationId });
  }

  const context = { projectId: row.projectId, taskId: row.taskId };
  if (row.config.modeId === trimmed) return ok(context);

  const updated = await client.updateConfig({
    conversationId,
    config: { ...row.config, modeId: trimmed },
  });
  if (!updated.success) {
    return err({ type: 'host-rejected', message: updated.error.message });
  }

  createConversationRegistry(deps.db).refresh(conversationId, {
    config: updated.data.config as ConversationConfig,
    updatedAt: new Date(updated.data.updatedAt).toISOString(),
    lastObservedAt: new Date().toISOString(),
  });

  return ok(context);
}
