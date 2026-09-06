import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { useMemo, useState } from 'react';
import { hostRefFromConnectionId } from '@core/features/agents/api/browser/client';
import { useAgentInstallationStatuses } from '@core/features/agents/api/browser/use-agent-installation-statuses';
import { useAgents } from '@core/features/agents/api/browser/use-agents';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { resolveConversationProviderSelection } from '../../browser/provider-selection';

export type EffectiveProvider = {
  providerId: AgentProviderId | null;
  setProviderOverride: (id: AgentProviderId | null) => void;
  installedProviderIds: AgentProviderId[];
  createDisabled: boolean;
};

export function useEffectiveProvider(
  connectionId?: string,
  initialOverride?: AgentProviderId
): EffectiveProvider {
  const [providerOverride, setProviderOverride] = useState<AgentProviderId | null>(
    initialOverride ?? null
  );

  const { value: defaultAgentValue } = useAppSettingsKey('defaultAgent');
  const host = hostRefFromConnectionId(connectionId);
  const { data: agents } = useAgents(host);
  const orderedProviderIds = useMemo(
    () => (agents ?? []).map((agent) => agent.id as AgentProviderId),
    [agents]
  );
  const defaultProviderId =
    defaultAgentValue && orderedProviderIds.includes(defaultAgentValue) ? defaultAgentValue : null;

  const { data: statuses } = useAgentInstallationStatuses(host);
  const availabilityKnown = statuses !== undefined;

  const installedProviderIds = useMemo(
    () =>
      (statuses ?? []).filter((s) => s.status === 'available').map((s) => s.id as AgentProviderId),
    [statuses]
  );

  const { providerId, createDisabled } = resolveConversationProviderSelection({
    orderedProviderIds,
    defaultProviderId,
    providerOverride,
    installedProviderIds,
    availabilityKnown,
  });

  return { providerId, setProviderOverride, installedProviderIds, createDisabled };
}
