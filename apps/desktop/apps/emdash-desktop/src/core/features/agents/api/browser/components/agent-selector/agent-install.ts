import type { AgentInstallError, AgentUpdateError } from '@core/primitives/agents/api';
import { getHostDependencyErrorMessage } from '@core/primitives/host-dependencies/browser/error-message';

export type AgentInstallActionState = {
  render: boolean;
  disabled: boolean;
  installing: boolean;
  label: string;
};

export function getAgentInstallActionState({
  agentName,
  canInstall,
  isInstalled,
  isInstalling,
}: {
  agentName: string;
  canInstall: boolean;
  isInstalled: boolean;
  isInstalling: boolean;
}): AgentInstallActionState {
  return {
    render: canInstall && !isInstalled,
    disabled: isInstalling,
    installing: isInstalling,
    label: `Install ${agentName}`,
  };
}

export type AgentUpdateActionState = {
  render: boolean;
  disabled: boolean;
  updating: boolean;
  label: string;
  versionLabel: string | null;
};

export function getAgentUpdateErrorMessage(error: AgentUpdateError): string {
  switch (error.type) {
    case 'no-update-strategy':
      return `No update strategy is available for ${error.id}.`;
    case 'not-detected-after-update':
      return 'The agent was not detected after update.';
    default:
      return getHostDependencyErrorMessage(error);
  }
}

export function getAgentOperationErrorMessage(error: AgentInstallError | AgentUpdateError): string {
  if (error.type === 'no-update-strategy' || error.type === 'not-detected-after-update') {
    return getAgentUpdateErrorMessage(error);
  }
  return getHostDependencyErrorMessage(error);
}

export function getAgentUpdateActionState({
  updateAvailable,
  updateStrategyKind,
  version,
  latestVersion,
  isUpdating,
}: {
  updateAvailable: boolean;
  updateStrategyKind: string;
  version: string | null;
  latestVersion: string | null;
  isUpdating: boolean;
}): AgentUpdateActionState {
  const canUpdate =
    updateAvailable && updateStrategyKind !== 'auto' && updateStrategyKind !== 'none';
  const versionLabel = version && latestVersion ? `v${version} → v${latestVersion}` : null;

  return {
    render: canUpdate,
    disabled: isUpdating,
    updating: isUpdating,
    label: isUpdating ? 'Updating...' : 'Update',
    versionLabel,
  };
}
