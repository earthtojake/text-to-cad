import type { HostRef } from '@emdash/core/primitives/host/api';
import type {
  ConversationIdRegime,
  CreateConversationInput,
} from '@emdash/core/runtimes/conversations/api';
import { log } from '@emdash/shared/logger';
import type { ConversationConfig } from '@core/primitives/conversations/api';
import type { ConversationsRuntimeBroker } from '../runtime-adapter';

/**
 * The id regime frozen into a host record at creation (spec §3.1). ACP providers mint
 * their session ids through `session/new`; PTY conversations get an emdash-chosen resume
 * handle seeded from the conversation id (provider hooks may later rebind the observed
 * `providerSessionId`, but the regime records who chose the handle emdash resumes with).
 */
export function conversationIdRegimeFor(type: 'acp' | 'pty'): ConversationIdRegime {
  return type === 'acp' ? 'provider-minted' : 'emdash-chosen';
}

/**
 * Builds the host index `create` payload with the Placement-computed path frozen in
 * (spec §6.1). Emdash sessions run in the workspace root, so `cwd` equals
 * `workspacePath`; the initial prompt queue rides `config`.
 */
export function buildHostConversationCreateInput(args: {
  id: string;
  provider: string;
  type: 'acp' | 'pty';
  title: string;
  workspacePath: string;
  config: ConversationConfig;
  createdAt: number;
}): CreateConversationInput {
  return {
    conversationId: args.id,
    provider: args.provider,
    type: args.type,
    cwd: args.workspacePath,
    workspacePath: args.workspacePath,
    idRegime: conversationIdRegimeFor(args.type),
    createdAt: args.createdAt,
    title: args.title,
    config: args.config,
  };
}

/**
 * Registers a conversation record in a host's index — the standalone foreground wire
 * request of the host-first creation flow (spec §6.2, step 2).
 */
export async function createHostConversationRecord(
  runtimes: ConversationsRuntimeBroker,
  host: HostRef,
  input: CreateConversationInput
): Promise<{ success: true } | { success: false; message: string }> {
  const client = await runtimes.client(host);
  if (!client.success) {
    return { success: false, message: client.error.message };
  }
  const created = await client.data.conversations.create(input);
  if (!created.success) {
    return { success: false, message: created.error.message };
  }
  return { success: true };
}

/**
 * The compensating delete of the host-first creation flow (spec §6.2, step 4): a direct
 * foreground index call, deliberately not the outbox delete verb — the host is reachable
 * by construction and no session exists yet. If this call itself fails, the record
 * orphans into the host's conversations surface; no queue is kept for it.
 */
export async function compensateHostConversationRecord(
  runtimes: ConversationsRuntimeBroker,
  host: HostRef,
  conversationId: string
): Promise<void> {
  try {
    const client = await runtimes.client(host);
    if (!client.success) throw new Error(client.error.message);
    await client.data.conversations.delete({ conversationId });
  } catch (error) {
    log.error('conversation create compensation failed; host record orphans', {
      conversationId,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}
