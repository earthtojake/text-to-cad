import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { Button, Popover } from '@emdash/ui/react/primitives';
import { Check, ChevronDown } from 'lucide-react';
import { useState } from 'react';
import { useAgentModels } from '@core/features/agents/api/browser/use-agent-models';
import { AgentIcon } from '@core/features/agents/contributions/browser/agent-icon';
import { CAD_CONVERSATION_PROVIDER_IDS } from '@core/features/cad/api/browser/cad-conversation-provider';
import { cn } from '@core/primitives/styling/browser/cn';

const PROVIDER_LABELS: Record<(typeof CAD_CONVERSATION_PROVIDER_IDS)[number], string> = {
  claude: 'Claude',
  codex: 'Codex',
};

export function NewChatAgentModelSelector({
  providerId,
  modelId,
  connectionId,
  installedProviderIds,
  disabled = false,
  onProviderChange,
  onModelChange,
}: {
  providerId: AgentProviderId | null;
  modelId: string | null;
  connectionId?: string;
  installedProviderIds: readonly AgentProviderId[];
  disabled?: boolean;
  onProviderChange: (providerId: AgentProviderId) => void;
  onModelChange: (modelId: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const {
    modelOptions: options,
    isLoading,
    error,
    refresh,
  } = useAgentModels(providerId, connectionId);
  const modelOptions = Object.entries(options ?? {}).map(([id, option]) => ({
    id,
    name: option.name,
  }));
  const selectedModel = modelOptions.find((option) => option.id === modelId);
  const providerLabel =
    providerId && providerId in PROVIDER_LABELS
      ? PROVIDER_LABELS[providerId as keyof typeof PROVIDER_LABELS]
      : 'Choose agent';
  const modelLabel = selectedModel?.name ?? modelId ?? 'Default';

  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next && providerId) void refresh();
      }}
    >
      <Popover.Trigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            aria-label="Choose agent and model"
            title={`${providerLabel} · ${modelLabel}`}
            className="h-7 max-w-56 min-w-0 justify-start gap-1.5 px-2 text-xs font-normal"
          >
            {providerId ? (
              <AgentIcon id={providerId} size={16} className="shrink-0 rounded-sm" />
            ) : null}
            <span className="shrink-0">{providerLabel}</span>
            <span className="text-foreground-passive">·</span>
            <span className="min-w-0 truncate text-foreground-muted">{modelLabel}</span>
            <ChevronDown className="size-3.5 shrink-0 text-foreground-muted" />
          </Button>
        }
      />
      <Popover.Content align="end" className="w-72 p-1">
        <div className="px-2 pt-1 pb-1 text-tiny font-medium text-foreground-muted">Agent</div>
        <div className="grid grid-cols-2 gap-1 px-1 pb-1">
          {CAD_CONVERSATION_PROVIDER_IDS.map((candidate) => {
            const isSelected = candidate === providerId;
            const isInstalled =
              isSelected || installedProviderIds.some((installed) => installed === candidate);
            return (
              <button
                key={candidate}
                type="button"
                disabled={!isInstalled}
                aria-pressed={isSelected}
                aria-label={
                  isInstalled
                    ? `Use ${PROVIDER_LABELS[candidate]}`
                    : `${PROVIDER_LABELS[candidate]} is not installed`
                }
                className={cn(
                  'flex h-9 min-w-0 items-center gap-2 rounded-md px-2 text-left text-xs transition-colors hover:bg-(--em-surface-hover) focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--em-border-focus) disabled:opacity-45',
                  isSelected && 'bg-(--em-surface-selected)'
                )}
                onClick={() => {
                  if (isSelected) return;
                  onProviderChange(candidate);
                  onModelChange(null);
                }}
              >
                <AgentIcon id={candidate} size={16} className="shrink-0 rounded-sm" />
                <span className="min-w-0 flex-1 truncate">{PROVIDER_LABELS[candidate]}</span>
                {isSelected ? <Check className="size-3.5 shrink-0" /> : null}
              </button>
            );
          })}
        </div>

        <div className="mx-1 border-t" />
        <div className="flex items-center justify-between px-2 pt-2 pb-1 text-tiny text-foreground-muted">
          <span>{isLoading ? 'Loading models…' : 'Model'}</span>
          <button type="button" disabled={isLoading || !providerId} onClick={() => void refresh()}>
            Refresh
          </button>
        </div>
        {error ? (
          <p className="px-2 py-1 text-xs text-foreground-muted">
            Couldn’t load models. Refresh or use the provider default.
          </p>
        ) : null}
        <div className="max-h-64 overflow-y-auto px-1 pb-1">
          <ModelOption
            label="Default (recommended)"
            selected={modelId === null}
            onSelect={() => {
              onModelChange(null);
              setOpen(false);
            }}
          />
          {modelOptions.map((option) => (
            <ModelOption
              key={option.id}
              label={option.name}
              selected={option.id === modelId}
              onSelect={() => {
                onModelChange(option.id);
                setOpen(false);
              }}
            />
          ))}
        </div>
      </Popover.Content>
    </Popover.Root>
  );
}

function ModelOption({
  label,
  selected,
  onSelect,
}: {
  label: string;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={cn(
        'flex min-h-8 w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-(--em-surface-hover) focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-(--em-border-focus)',
        selected && 'bg-(--em-surface-selected)'
      )}
      onClick={onSelect}
    >
      <span className="min-w-0 flex-1">{label}</span>
      {selected ? <Check className="size-3.5 shrink-0" /> : null}
    </button>
  );
}
