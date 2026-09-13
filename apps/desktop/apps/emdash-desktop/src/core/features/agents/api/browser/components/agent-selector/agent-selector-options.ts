import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { agentSupportsAcp, type AgentPayload } from '@core/primitives/agents/api';
import { getAgentInstallActionState } from './agent-install';

export type AgentDisableReason = (
  agent: Pick<AgentPayload, 'id' | 'name' | 'capabilities'>
) => string | null | undefined;

export interface AgentOption {
  value: string;
  label: string;
  agentId: AgentProviderId;
  disabled: boolean;
  disabledReason?: string;
  canInstall: boolean;
  supportsAcp: boolean;
}

export interface AgentGroup {
  value: string;
  label: string;
  items: AgentOption[];
}

export function buildAgentGroups(
  agents: readonly Pick<AgentPayload, 'id' | 'name' | 'capabilities'>[],
  installedAgents: string[],
  assumedInstalledAgents: string[] = [],
  installingAgents: ReadonlySet<AgentProviderId> = new Set(),
  getDisabledReason?: AgentDisableReason
): AgentGroup[] {
  const allAgentIds = agents.map((agent) => agent.id as AgentProviderId);
  const agentNames = new Map(agents.map((agent) => [agent.id, agent.name]));
  const agentById = new Map(agents.map((agent) => [agent.id, agent]));
  const agentAcpSupport = new Map(
    agents.map((agent) => [agent.id, agentSupportsAcp(agent.capabilities)])
  );
  const installedSet = new Set(
    [...installedAgents, ...assumedInstalledAgents].filter((id) =>
      allAgentIds.includes(id as AgentProviderId)
    )
  );

  const resolveName = (id: AgentProviderId) => agentNames.get(id) ?? id;
  const supportsAcp = (id: AgentProviderId) => agentAcpSupport.get(id) ?? false;
  const disabledReason = (id: AgentProviderId) => {
    const agent = agentById.get(id);
    return agent ? (getDisabledReason?.(agent) ?? undefined) : undefined;
  };

  const installedOptions: AgentOption[] = allAgentIds
    .filter((id) => installedSet.has(id) && !installingAgents.has(id))
    .map((id) => {
      const reason = disabledReason(id);
      return {
        value: id,
        label: resolveName(id),
        agentId: id,
        disabled: Boolean(reason),
        disabledReason: reason,
        canInstall: false,
        supportsAcp: supportsAcp(id),
      };
    });

  const notInstalledOptions: AgentOption[] = allAgentIds
    .filter((id) => !installedSet.has(id) || installingAgents.has(id))
    .map((id) => ({
      value: id,
      label: resolveName(id),
      agentId: id,
      disabled: true,
      canInstall: true,
      supportsAcp: supportsAcp(id),
    }));

  return [
    { value: 'installed', label: 'Installed', items: installedOptions },
    { value: 'not-installed', label: 'Not installed', items: notInstalledOptions },
  ].filter((group) => group.items.length > 0);
}

export function canInstallAgentOption(item: AgentOption, allowInstall: boolean): boolean {
  return allowInstall && item.canInstall;
}

export function getAssumedInstalledAgents(
  value: AgentProviderId | null,
  dependencyData: Record<string, unknown> | null
): AgentProviderId[] {
  return value && dependencyData?.[value] === undefined ? [value] : [];
}

export function isComboboxOptionDisabled(item: AgentOption): boolean {
  return item.disabled;
}

export function getInstallButtonState(
  item: AgentOption,
  allowInstall: boolean,
  installingAgents: ReadonlySet<AgentProviderId>
): { render: boolean; disabled: boolean; installing: boolean; label: string } {
  return getAgentInstallActionState({
    agentName: item.label,
    canInstall: allowInstall && item.canInstall,
    isInstalled: !item.canInstall,
    isInstalling: installingAgents.has(item.agentId),
  });
}
