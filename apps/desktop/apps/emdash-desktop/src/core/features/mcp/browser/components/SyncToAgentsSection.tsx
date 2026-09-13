import { sshConnectionIdOf, type HostRef } from '@emdash/core/primitives/host/api';
import type { McpProvidersResponse } from '@emdash/core/primitives/mcp/api';
import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { Button, Field } from '@emdash/ui/react/primitives';
import { X } from 'lucide-react';
import React from 'react';
import { AgentIcon } from '@core/features/agents/contributions/browser/agent-icon';
import { AgentSelector } from '@core/features/agents/contributions/browser/agent-selector';
import { cn } from '@core/primitives/styling/browser/cn';

interface SyncToAgentsSectionProps {
  host: HostRef;
  providers: McpProvidersResponse[];
  selectedProviders: string[];
  onToggle: (id: string) => void;
  onSetAll: (ids: string[]) => void;
}

export const SyncToAgentsSection: React.FC<SyncToAgentsSectionProps> = ({
  host,
  providers,
  selectedProviders,
  onToggle,
  onSetAll,
}) => {
  const selectedProviderIds = new Set(selectedProviders);
  const providersById = new Map(providers.map((provider) => [provider.id, provider]));
  const selected = selectedProviders
    .map((id) => providersById.get(id))
    .filter((provider): provider is McpProvidersResponse => Boolean(provider));
  const installedProviders = providers.filter((provider) => provider.installed);

  return (
    <Field.Root>
      <div className="flex items-center justify-between gap-3">
        <Field.Label>Sync to agents</Field.Label>
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-auto p-0 text-xs"
          disabled={installedProviders.length === 0}
          onClick={() => onSetAll(installedProviders.map((provider) => provider.id))}
        >
          Sync to all installed agents
        </Button>
      </div>
      <div className="flex flex-wrap gap-2">
        {selected.map((provider) => (
          <div
            key={provider.id}
            className={cn(
              'group relative inline-flex h-8 items-center gap-1.5 rounded-full border border-border-primary bg-foreground/10 pr-3 pl-2 text-xs text-foreground ring-1 ring-ring/30 transition-colors',
              'hover:border-border-destructive/60 hover:bg-background-destructive hover:text-foreground-destructive'
            )}
            title={`Synced to ${provider.name}`}
          >
            <AgentIcon
              id={provider.id as AgentProviderId}
              size={16}
              className="rounded-sm transition-opacity group-hover:opacity-35"
            />
            <span className="transition-opacity group-hover:opacity-35">{provider.name}</span>
            <button
              type="button"
              className="absolute right-2 opacity-0 transition-opacity group-hover:opacity-100"
              onClick={() => onToggle(provider.id)}
              aria-label={`Remove ${provider.name} from synced agents`}
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        ))}
        <AgentSelector
          value={null}
          placeholder="Select agent"
          connectionId={sshConnectionIdOf(host)}
          onChange={(id) => {
            if (!selectedProviderIds.has(id)) onToggle(id);
          }}
          className="h-8 w-44 rounded-full border-dashed text-xs"
          contentClassName="w-72"
        />
      </div>
    </Field.Root>
  );
};
