import type { AgentProviderId } from '@emdash/plugins/agents/types';

type ConversationTitleInput = {
  providerId: AgentProviderId;
  title: string;
};

function capitalizeProviderId(providerId: AgentProviderId): string {
  return `${providerId.charAt(0).toUpperCase()}${providerId.slice(1)}`;
}

function parseDefaultTitleIndex(title: string, providerId: AgentProviderId): number | null {
  const match = title.match(new RegExp(`^${providerId} \\(([1-9]\\d*)\\)$`, 'i'));
  if (!match) return null;

  const rawIndex = match[1];
  const index = Number(rawIndex);
  if (!Number.isInteger(index) || index < 1) return null;
  if (String(index) !== rawIndex) return null;
  return index;
}

export function formatConversationTitleForDisplay(
  providerId: AgentProviderId,
  title: string
): string {
  const index = parseDefaultTitleIndex(title, providerId);
  if (index === null) return title;
  return `${capitalizeProviderId(providerId)} (${index})`;
}

export function nextDefaultConversationTitle(
  providerId: AgentProviderId,
  conversations: ConversationTitleInput[]
): string {
  const used = new Set<number>();

  for (const conversation of conversations) {
    if (conversation.providerId !== providerId) continue;
    const index = parseDefaultTitleIndex(conversation.title, providerId);
    if (index !== null) used.add(index);
  }

  let next = 1;
  while (used.has(next)) next += 1;

  return `${capitalizeProviderId(providerId)} (${next})`;
}
