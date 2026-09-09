import { Checkbox } from '@emdash/ui/react/primitives';
import { useRef, type ReactNode } from 'react';
import { cn } from '@core/primitives/styling/browser/cn';
export function ConversationSelectionControl({
  label,
  selected,
  disabled,
  onToggle,
  onRangeStep,
  selectionId,
  children,
}: {
  label: string;
  selected: boolean;
  disabled?: boolean;
  onToggle: (shiftKey: boolean) => void;
  onRangeStep?: (direction: -1 | 1) => void;
  selectionId?: string;
  children?: ReactNode;
}) {
  const shiftKeyRef = useRef(false);

  return (
    <span className="relative flex h-full w-7 shrink-0 items-center justify-center">
      <span
        data-slot="conversation-trailing-value"
        className={cn(
          'absolute inset-0 flex items-center justify-center transition-opacity',
          'group-hover/conversation:opacity-0 group-focus-within/conversation:opacity-0',
          selected && 'opacity-0'
        )}
      >
        {children}
      </span>
      <span
        data-slot="conversation-selection-checkbox"
        className={cn(
          'absolute inset-0 flex items-center justify-center transition-opacity',
          'opacity-0 group-hover/conversation:opacity-100 group-focus-within/conversation:opacity-100',
          selected && 'opacity-100'
        )}
        onPointerDownCapture={(event) => {
          shiftKeyRef.current = event.shiftKey;
        }}
        onKeyDownCapture={(event) => {
          shiftKeyRef.current = event.shiftKey;
        }}
        onClick={(event) => event.stopPropagation()}
        onDoubleClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          event.stopPropagation();
          if (disabled || !event.shiftKey || !onRangeStep) return;
          if (event.key === 'ArrowUp') {
            event.preventDefault();
            onRangeStep(-1);
          } else if (event.key === 'ArrowDown') {
            event.preventDefault();
            onRangeStep(1);
          }
        }}
        onPointerDown={(event) => event.stopPropagation()}
      >
        <Checkbox
          checked={selected}
          disabled={disabled}
          onCheckedChange={() => {
            const shiftKey = shiftKeyRef.current;
            shiftKeyRef.current = false;
            onToggle(shiftKey);
          }}
          data-conversation-selection-id={selectionId}
          aria-label={label}
        />
      </span>
    </span>
  );
}
