import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import type { AppDb } from '@core/services/app-db/node/db';

/** Seen-state is a device-local client annotation (spec §3.2) — never a host fact. */
export async function markConversationSeen(db: AppDb, conversationId: string): Promise<void> {
  createConversationRegistry(db).annotate(conversationId, { agentStatusSeen: 1 });
}
