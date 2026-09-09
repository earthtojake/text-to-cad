import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { useMemo } from 'react';
import { hostRefFromConnectionId } from '@core/features/agents/api/browser/client';
import { useAgentInstallationStatuses } from '@core/features/agents/api/browser/use-agent-installation-statuses';
import { useAgents } from '@core/features/agents/api/browser/use-agents';
import {
  buildAgentGroups,
  getAssumedInstalledAgents,
  type AgentDisableReason,
} from './agent-selector-options';

export function useAgentAvailability({
  connectionId,
  getDisabledReason,
  value,
}: {
  connectionId?: string;
  getDisabledReason?: AgentDisableReason;
  value: AgentProviderId | null;
}) {
  const host = hostRefFromConnectionId(connectionId);
  const { data: agents } = useAgents(host);
  const { data: statuses, install, isInstalling } = useAgentInstallationStatuses(host);

  const dependencyData = useMemo(() => {
    if (!statuses) return null;
    const result: Record<string, { status: string; category: string }> = {};
    for (const s of statuses) {
      result[s.id] = { status: s.status, category: 'agent' };
    }
    return result;
  }, [statuses]);

  const installedAgents = useMemo(
    () =>
      dependencyData
        ? Object.entries(dependencyData)
            .filter(([, state]) => state.category === 'agent' && state.status === 'available')
            .map(([id]) => id)
        : [],
    [dependencyData]
  );

  const assumedInstalledAgents = useMemo(
    () => getAssumedInstalledAgents(value, dependencyData),
    [value, dependencyData]
  );

  const installingAgents = new Set<AgentProviderId>();

  const groups = buildAgentGroups(
    agents ?? [],
    installedAgents,
    assumedInstalledAgents,
    installingAgents,
    getDisabledReason
  );

  async function installAgent(agentId: AgentProviderId): Promise<void> {
    return new Promise((resolve) => {
      install({ id: agentId }, { onSettled: () => resolve() });
    });
  }

  return {
    groups,
    dependencyData,
    installingAgents,
    installAgent,
    isInstalling,
  };
}
