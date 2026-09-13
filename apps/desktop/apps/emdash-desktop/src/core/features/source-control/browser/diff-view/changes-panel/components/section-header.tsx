import { Badge, Checkbox } from '@emdash/ui/react/primitives';
import { ChevronDown } from 'lucide-react';
import { cn } from '@core/primitives/styling/browser/cn';
import { type SelectionState } from '../../stores/changes-view-store';

interface SectionHeaderProps {
  label: string;
  count: number;
  selectionState?: SelectionState;
  onToggleAll?: () => void;
  actions?: React.ReactNode;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}

export function SectionHeader({
  label,
  count,
  selectionState,
  onToggleAll,
  actions,
  collapsed,
  onToggleCollapsed,
}: SectionHeaderProps) {
  const showCheckbox = selectionState !== undefined && onToggleAll !== undefined;
  return (
    // Inert fixed-height row rendered as a direct child of the sections
    // Resizable.Group (the library ignores non-panel children for layout
    // math). Headers draw the section dividers; the resize handles between
    // expanded bodies are ghost handles.
    <div className="flex h-10 shrink-0 items-center justify-between gap-2 border-t border-border px-3.5 first:border-t-0">
      <button onClick={onToggleCollapsed} className="min-w-0">
        <span className="flex min-w-0 items-center gap-2 text-sm text-foreground-muted">
          <span className="truncate">{label}</span> <Badge>{count}</Badge>{' '}
          <span className="p-2 text-foreground-muted hover:text-foreground">
            <ChevronDown
              className={cn(
                'size-4 transition-transform duration-200 ease-in-out',
                collapsed ? '-rotate-90' : 'rotate-0'
              )}
            />
          </span>
        </span>
      </button>
      <div className="flex items-center gap-1.5">
        {actions}
        {showCheckbox && (
          <Checkbox
            checked={selectionState === 'all'}
            indeterminate={selectionState === 'partial'}
            onCheckedChange={onToggleAll}
            aria-label={`Select all ${label.toLowerCase()}`}
            className="mr-0.5"
          />
        )}
      </div>
    </div>
  );
}
