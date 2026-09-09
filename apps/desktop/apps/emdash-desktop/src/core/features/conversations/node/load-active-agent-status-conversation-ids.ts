import { isLocalHostRef, type HostRef } from '@emdash/core/primitives/host/api';
import { and, eq, inArray, isNull } from 'drizzle-orm';
import {
  conversationRegistryTable as conversations,
  liveConversations,
} from '@core/features/conversations/api/node/registry';
import type { AppDb } from '@core/services/app-db/node/db';

export async function loadActiveAgentStatusConversationIds(
  db: AppDb,
  host: HostRef,
  conversationType: 'acp' | 'pty'
): Promise<string[]> {
  const hostIdentity = isLocalHostRef(host)
    ? and(eq(conversations.location, 'local'), isNull(conversations.sshConnectionId))
    : and(eq(conversations.location, 'remote'), eq(conversations.sshConnectionId, host.id));
  const rows = await db
    .select({ id: conversations.id })
    .from(conversations)
    .where(
      and(
        liveConversations(),
        hostIdentity,
        eq(conversations.type, conversationType),
        inArray(conversations.agentStatus, ['working', 'awaiting-input'])
      )
    );
  return rows.map((row) => row.id);
}
