import { Button, Tooltip } from '@emdash/ui/react/primitives';
import { AlignJustify, ListTree } from 'lucide-react';
import { useState } from 'react';
import type { ChangesListViewMode } from '@core/primitives/app-settings/api';

interface ChangesViewModeToggleProps {
  value: ChangesListViewMode;
  onChange: (mode: ChangesListViewMode) => void;
  label: string;
}

export function ChangesViewModeToggle({ value, onChange, label }: ChangesViewModeToggleProps) {
  const nextMode: ChangesListViewMode = value === 'flat' ? 'tree' : 'flat';
  const Icon = value === 'flat' ? AlignJustify : ListTree;
  const tooltip = value === 'flat' ? 'Switch to tree view' : 'Switch to flat list';
  const [open, setOpen] = useState(false);

  return (
    <Tooltip.Root
      open={open}
      onOpenChange={(nextOpen, details) => {
        // Keep the tooltip visible after a click so the user can read the
        // updated label that reflects the new view mode.
        if (!nextOpen && details.reason === 'trigger-press') return;
        setOpen(nextOpen);
      }}
    >
      <Tooltip.Trigger
        render={
          <Button
            variant="ghost"
            size="xs"
            icon
            onClick={() => onChange(nextMode)}
            aria-label={`${tooltip} (${label})`}
          >
            <Icon className="size-3" />
          </Button>
        }
      />
      <Tooltip.Content>{tooltip}</Tooltip.Content>
    </Tooltip.Root>
  );
}
