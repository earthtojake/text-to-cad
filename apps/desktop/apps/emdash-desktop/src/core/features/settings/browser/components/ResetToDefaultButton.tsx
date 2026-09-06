import { Button, Tooltip } from '@emdash/ui/react/primitives';
import { RotateCcw } from 'lucide-react';
import React from 'react';

interface ResetToDefaultButtonProps {
  /** Optional label shown in the tooltip: "Reset to default: <label>" */
  defaultLabel?: string;
  onReset: () => void;
  disabled?: boolean;
  visible?: boolean;
}

export const ResetToDefaultButton: React.FC<ResetToDefaultButtonProps> = ({
  defaultLabel,
  onReset,
  disabled,
  visible = true,
}) => {
  if (!visible) {
    return <span aria-hidden="true" className="h-7 w-7 shrink-0" />;
  }

  return (
    <Tooltip.Provider delay={150}>
      <Tooltip.Root>
        <Tooltip.Trigger
          render={
            <Button
              type="button"
              variant="ghost"
              icon
              className="h-7 w-7 shrink-0 text-foreground-muted hover:text-foreground"
              onClick={onReset}
              disabled={disabled}
              aria-label="Reset to default"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
          }
        />
        <Tooltip.Content side="top">
          {defaultLabel !== undefined ? `Reset to default: ${defaultLabel}` : 'Reset to default'}
        </Tooltip.Content>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
};
