import type { AgentProviderId } from '@emdash/plugins/agents/types';

type ResolveConversationProviderSelectionParams = {
  orderedProviderIds: AgentProviderId[];
  defaultProviderId: AgentProviderId | null;
  providerOverride: AgentProviderId | null;
  installedProviderIds: AgentProviderId[];
  availabilityKnown: boolean;
};

export type ConversationProviderSelection = {
  providerId: AgentProviderId | null;
  createDisabled: boolean;
};

export function resolveConversationProviderSelection({
  orderedProviderIds,
  defaultProviderId,
  providerOverride,
  installedProviderIds,
  availabilityKnown,
}: ResolveConversationProviderSelectionParams): ConversationProviderSelection {
  const installedSet = new Set(installedProviderIds);
  const fallbackProviderId =
    availabilityKnown && (!defaultProviderId || !installedSet.has(defaultProviderId))
      ? orderedProviderIds.find((id) => installedSet.has(id))
      : undefined;

  const noInstalledAgents = availabilityKnown && installedSet.size === 0;
  const effectiveDefaultProviderId = noInstalledAgents
    ? null
    : (fallbackProviderId ?? defaultProviderId);
  const providerId = providerOverride ?? effectiveDefaultProviderId;
  const providerInstalled = providerId ? installedSet.has(providerId) : false;

  return {
    providerId,
    createDisabled: providerId === null || (availabilityKnown && !providerInstalled),
  };
}
