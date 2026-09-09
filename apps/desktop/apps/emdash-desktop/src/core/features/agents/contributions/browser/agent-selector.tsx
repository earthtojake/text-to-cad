import type { ComboboxRootChangeEventDetails } from '@base-ui/react/combobox';
import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { Pill } from '@emdash/ui/react/components';
import { Combobox } from '@emdash/ui/react/primitives';
import { ChevronDown } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import React, { useMemo, useState } from 'react';
import {
  canInstallAgentOption,
  isComboboxOptionDisabled,
  type AgentDisableReason,
  type AgentGroup,
  type AgentOption,
} from '@core/features/agents/api/browser/components/agent-selector/agent-selector-options';
import { useAgentAvailability } from '@core/features/agents/api/browser/components/agent-selector/use-agent-availability';
import {
  AgentHoverCard,
  isEventInsideAgentHoverCard,
  useAgentHoverCard,
} from '@core/features/agents/browser/components/agent-selector/agent-hover-card';
import { AgentIcon } from '@core/features/agents/contributions/browser/agent-icon';
import { cn } from '@core/primitives/styling/browser/cn';

interface AgentSelectorProps {
  value: AgentProviderId | null;
  onChange: (agent: AgentProviderId) => void;
  disabled?: boolean;
  className?: string;
  contentClassName?: string;
  connectionId?: string;
  getDisabledReason?: AgentDisableReason;
  installable?: boolean;
  autoFocus?: boolean;
  placeholder?: string;
  ariaLabel?: string;
  allowedAgentIds?: readonly AgentProviderId[];
  agentLabelOverrides?: Readonly<Record<string, string>>;
  simplified?: boolean;
}

export const AgentSelector: React.FC<AgentSelectorProps> = observer(
  ({
    value,
    onChange,
    disabled = false,
    className = '',
    contentClassName,
    connectionId,
    getDisabledReason,
    installable = true,
    autoFocus = false,
    placeholder = 'No agent installed',
    ariaLabel,
    allowedAgentIds,
    agentLabelOverrides,
    simplified = false,
  }) => {
    const [open, setOpen] = useState(false);
    const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
    const hoverCard = useAgentHoverCard();
    const { groups } = useAgentAvailability({
      connectionId,
      getDisabledReason,
      value,
    });
    const visibleGroups = useMemo(() => {
      if (!allowedAgentIds) return groups;
      const allowed = new Set(allowedAgentIds);
      return groups
        .map((group) => ({
          ...group,
          items: group.items.filter((item) => allowed.has(item.agentId)),
        }))
        .filter((group) => group.items.length > 0);
    }, [allowedAgentIds, groups]);
    const allOptions = useMemo(
      () => visibleGroups.flatMap((group) => group.items),
      [visibleGroups]
    );

    const selectedOption = value ? allOptions.find((o) => o.value === value) : null;
    const displayLabel = (option: AgentOption) =>
      agentLabelOverrides?.[option.agentId] ?? option.label;

    function handleOpenChange(next: boolean, eventDetails: ComboboxRootChangeEventDetails) {
      if (disabled) return;
      // Clicks/focus inside the hover card register as outside presses on the combobox;
      // they must not dismiss the agent list (which would unmount the card too).
      if (!next && hoverCard.open && isEventInsideAgentHoverCard(eventDetails.event, anchorEl)) {
        eventDetails.cancel();
        return;
      }
      if (!next) hoverCard.close();
      setOpen(next);
    }

    function handleValueChange(item: AgentOption | null) {
      if (!item || disabled || item.disabled) return;
      hoverCard.close();
      onChange(item.agentId);
      setOpen(false);
    }

    return (
      <Combobox.Root
        items={visibleGroups}
        value={selectedOption ?? null}
        onValueChange={handleValueChange}
        open={open}
        onOpenChange={disabled ? undefined : handleOpenChange}
        isItemEqualToValue={(a: AgentOption, b: AgentOption) => a.value === b.value}
        filter={(item: AgentOption, query) =>
          displayLabel(item).toLowerCase().includes(query.toLowerCase())
        }
        autoHighlight
      >
        <Combobox.Trigger
          data-autofocus={autoFocus || undefined}
          aria-label={ariaLabel}
          disabled={disabled}
          className={cn(
            'flex h-9 w-full min-w-0 items-center gap-2 rounded-lg border border-border bg-transparent px-2.5 py-1 text-sm outline-none',
            disabled && 'cursor-not-allowed opacity-60',
            className
          )}
        >
          {value ? (
            <>
              <AgentIcon id={value} size={16} className="rounded-sm" />
              <span className="flex-1 truncate text-left">
                {selectedOption ? displayLabel(selectedOption) : value}
              </span>
            </>
          ) : (
            <span className="flex-1 truncate text-foreground-muted">{placeholder}</span>
          )}
          <ChevronDown className="size-3.5 shrink-0 text-foreground-muted" />
        </Combobox.Trigger>
        <Combobox.Content
          ref={setAnchorEl}
          className={cn('min-w-(--anchor-width)', contentClassName)}
        >
          {!simplified ? (
            <Combobox.Input showTrigger={false} placeholder="Search agents..." />
          ) : null}
          <Combobox.List className="pb-0">
            {(group: AgentGroup) => (
              <Combobox.Group key={group.value} items={group.items} className="py-1">
                {!simplified ? <Combobox.Label>{group.label}</Combobox.Label> : null}
                <Combobox.Collection>
                  {(item: AgentOption) => {
                    const showInstall = canInstallAgentOption(item, installable);
                    return (
                      <Combobox.Item
                        key={item.value}
                        value={item}
                        disabled={isComboboxOptionDisabled(item)}
                        hoverableWhenDisabled={item.disabled}
                        className={cn(
                          'group/agent-row',
                          showInstall && 'data-disabled:opacity-100'
                        )}
                        {...(!simplified ? hoverCard.getRowHoverProps(item.agentId) : {})}
                      >
                        <AgentIcon
                          id={item.agentId}
                          size={16}
                          className={cn('rounded-sm', showInstall && 'opacity-50')}
                        />
                        <span className="min-w-0 flex-1">
                          <span
                            className={cn('block truncate', showInstall && 'text-foreground-muted')}
                          >
                            {displayLabel(item)}
                          </span>
                          {item.disabledReason ? (
                            <span className="block truncate text-xs text-foreground-muted">
                              {item.disabledReason}
                            </span>
                          ) : null}
                        </span>
                        {!simplified && item.supportsAcp ? (
                          <Pill variant="info">Chat UI</Pill>
                        ) : null}
                      </Combobox.Item>
                    );
                  }}
                </Combobox.Collection>
              </Combobox.Group>
            )}
          </Combobox.List>
        </Combobox.Content>
        {!simplified ? (
          <AgentHoverCard anchor={anchorEl} controller={hoverCard} connectionId={connectionId} />
        ) : null}
      </Combobox.Root>
    );
  }
);
