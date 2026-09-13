import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { Button, Switch } from '@emdash/ui/react/primitives';
import { ExternalLink } from 'lucide-react';
import React from 'react';
import { hostRefFromConnectionId } from '@core/features/agents/api/browser/client';
import { useAgentInstallationStatus } from '@core/features/agents/api/browser/use-agent-installation-statuses';
import { useAgent } from '@core/features/agents/api/browser/use-agents';
import { AgentIcon } from '@core/features/agents/contributions/browser/agent-icon';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { InstallSection } from '@core/features/settings/contributions/browser/agents-page/InstallSection';
import type { AppSettings } from '@core/services/settings/api';

type Props = {
  id: AgentProviderId;
  connectionId?: string;
};

export const AgentInfoCard: React.FC<Props> = ({ id, connectionId }) => {
  const host = hostRefFromConnectionId(connectionId);
  const { data: payload } = useAgent(id, host);
  const { data: statusData } = useAgentInstallationStatus(id, host);
  const {
    value: defaultAgent,
    update: updateDefaultAgent,
    isLoading: isDefaultAgentLoading,
    isSaving: isDefaultAgentSaving,
  } = useAppSettingsKey('defaultAgent');

  const isInstalled = (statusData?.status ?? payload?.status) === 'available';
  const isDefaultAgent = defaultAgent === id;
  const title = payload?.name ?? id;
  const description = payload?.description ?? null;
  const docUrl = payload?.websiteUrl ?? null;

  function handleSetDefaultAgent(checked: boolean) {
    if (!checked || isDefaultAgent) return;
    updateDefaultAgent(id as AppSettings['defaultAgent']);
  }

  return (
    <div className="w-96 bg-background-quaternary p-3">
      <div className="mb-2 flex items-center justify-between gap-1.5">
        <div className="flex items-center gap-2 text-sm">
          <AgentIcon id={id} size={16} className="rounded-sm" />
          <span className="text-sm text-foreground">{title}</span>
        </div>
        {docUrl && (
          <Button
            variant="ghost"
            size="xs"
            className="p-0 text-foreground-muted"
            onClick={() => window.open(docUrl, '_blank', 'noreferrer')}
          >
            View Website
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        )}
      </div>

      {description ? (
        <p className="mb-2 text-xs leading-relaxed text-foreground-muted">{description}</p>
      ) : null}

      <div className="mb-3 flex items-center justify-between gap-3 rounded-md border border-border bg-background-1 px-2.5 py-2">
        <label
          htmlFor={`set-default-agent-${id}`}
          className="min-w-0 flex-1 text-xs text-foreground"
        >
          Set as the default agent
        </label>
        <Switch
          id={`set-default-agent-${id}`}
          size="sm"
          checked={isDefaultAgent}
          disabled={!isInstalled || isDefaultAgentLoading || isDefaultAgentSaving}
          onCheckedChange={handleSetDefaultAgent}
        />
      </div>

      {payload && (
        <InstallSection
          agentId={id}
          connectionId={connectionId}
          agentPayload={payload}
          installOptions={payload.installOptions}
          hideOverrideOptions={!isInstalled || !!connectionId}
          compact
        />
      )}
    </div>
  );
};
