import type { AgentProviderId } from '@emdash/plugins/agents/types';

export const CAD_CONVERSATION_PROVIDER_IDS = [
  'claude',
  'codex',
] as const satisfies readonly AgentProviderId[];

const STORAGE_PREFIX = 'hardcore:cad:new-chat-agent';

function storageKey(connectionId?: string): string {
  return connectionId ? `${STORAGE_PREFIX}:${connectionId}` : `${STORAGE_PREFIX}:local`;
}

function isCadConversationProvider(value: string | null): value is AgentProviderId {
  return CAD_CONVERSATION_PROVIDER_IDS.some((providerId) => providerId === value);
}

export function readLastCadConversationProvider(
  storage: Pick<Storage, 'getItem'>,
  connectionId?: string
): AgentProviderId | undefined {
  try {
    const value = storage.getItem(storageKey(connectionId));
    return isCadConversationProvider(value) ? value : undefined;
  } catch {
    return undefined;
  }
}

export function rememberCadConversationProvider(
  storage: Pick<Storage, 'setItem'>,
  providerId: AgentProviderId,
  connectionId?: string
): void {
  if (!isCadConversationProvider(providerId)) return;
  try {
    storage.setItem(storageKey(connectionId), providerId);
  } catch {
    // Storage can be unavailable in hardened renderer sessions; the in-memory choice still works.
  }
}
