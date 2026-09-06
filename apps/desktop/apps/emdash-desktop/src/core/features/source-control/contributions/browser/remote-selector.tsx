import { ComboboxPopover } from '@emdash/ui/react/components';
import type { ReactNode } from 'react';
import type { GitRemote } from '@core/primitives/git/api';

export interface RemoteSelectorSpecialOption {
  value: string;
  label: string;
}

export interface RemoteSelectorItem {
  value: string;
  label: string;
  url?: string;
  special?: boolean;
}

export interface RemoteSelectorProps {
  remotes: GitRemote[];
  value: string;
  onValueChange: (value: string) => void;
  specialOptions?: RemoteSelectorSpecialOption[];
  renderTrigger?: (selected: RemoteSelectorItem | null) => ReactNode;
  appearance?: 'control' | 'input';
  className?: string;
  contentClassName?: string;
  onOpenChange?: (open: boolean) => void;
  disabled?: boolean;
}

export function RemoteSelector({
  remotes,
  value,
  onValueChange,
  specialOptions = [],
  renderTrigger,
  appearance = 'input',
  className,
  contentClassName,
  onOpenChange,
  disabled,
}: RemoteSelectorProps) {
  const items: RemoteSelectorItem[] = [
    ...specialOptions.map((option) => ({ ...option, special: true })),
    ...remotes.map((remote) => ({
      value: remote.name,
      label: remote.name,
      url: remote.url,
    })),
  ];

  if (!items.some((item) => item.value === value)) {
    items.push({ value, label: value });
  }

  return (
    <ComboboxPopover
      items={items}
      value={value}
      onValueChange={onValueChange}
      onOpenChange={onOpenChange}
      itemToKey={(item) => item.value}
      itemToLabel={(item) => item.label}
      filter={(item, query) => {
        const normalizedQuery = query.trim().toLowerCase();
        if (!normalizedQuery) return true;
        return `${item.label} ${item.url ?? ''}`.toLowerCase().includes(normalizedQuery);
      }}
      renderTrigger={(selected) =>
        renderTrigger ? renderTrigger(selected) : (selected?.label ?? value)
      }
      triggerTitle={(selected) => selected?.url ?? selected?.label ?? value}
      renderItem={(item) => (
        <span className="flex min-w-0 flex-1 items-center gap-2 py-0.5">
          <span className={item.special ? 'font-medium' : 'shrink-0'}>{item.label}</span>
          {item.url ? (
            <span
              className="min-w-0 flex-1 truncate text-xs text-foreground-muted"
              title={item.url}
            >
              {item.url}
            </span>
          ) : null}
        </span>
      )}
      searchPlaceholder="Search remotes…"
      appearance={appearance}
      className={className}
      contentClassName={contentClassName}
      contentWidth="trigger"
      disabled={disabled}
    />
  );
}
