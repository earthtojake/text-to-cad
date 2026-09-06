import {
  formatHostRef,
  hostRefFromParts,
  type HostRef,
  type SerializedHostRef,
} from '@emdash/core/primitives/host/api';
import { eq } from 'drizzle-orm';
import { conversationRegistryTable as conversations } from '@core/features/conversations/api/node/registry';
import type {
  ConversationsHostRuntimesClient,
  ConversationsRuntimeBroker,
} from '@core/features/conversations/api/runtime-adapter';
import type { AppDb } from '@core/services/app-db/node/db';

export type HostConversationMutationDeps = {
  db: AppDb;
  runtimes: ConversationsRuntimeBroker;
  hostIsReachable: (hostRef: SerializedHostRef) => boolean;
};

export type ResolvedConversationHost = {
  row: typeof conversations.$inferSelect;
  host: HostRef;
  client: ConversationsHostRuntimesClient['conversations'];
};

/**
 * Resolves a cached conversation row to its source host's index client for a foreground
 * wire mutation (spec §4.3): edits are host-gated — an unreachable remote host refuses
 * the edit outright (same rule as creation; no offline queue, no local dirty state).
 */
export async function resolveConversationHostClient(
  deps: HostConversationMutationDeps,
  conversationId: string
): Promise<ResolvedConversationHost> {
  const [row] = await deps.db
    .select()
    .from(conversations)
    .where(eq(conversations.id, conversationId))
    .limit(1);
  if (!row) throw new Error(`Conversation not found: ${conversationId}`);

  const host = hostRefFromParts(row.location, row.sshConnectionId);
  if (host.type === 'remote' && !deps.hostIsReachable(formatHostRef(host))) {
    throw new Error('The workspace host is offline. Reconnect the machine to edit conversations.');
  }
  const client = await deps.runtimes.client(host);
  if (!client.success) {
    throw new Error(`The conversation's host is unavailable: ${client.error.message}`);
  }
  return { row, host, client: client.data.conversations };
}
