import type { GitChange, GitChangeStatus } from '@emdash/core/runtimes/git/api';
import { Checkbox } from '@emdash/ui/react/primitives';
import { SquareArrowRight, SquareDot, SquareMinus, SquarePlus, SquareX } from 'lucide-react';
import { forwardRef, useMemo, type ButtonHTMLAttributes } from 'react';
import { FileIcon } from '@core/features/editor/contributions/browser/file-icon';
import { splitPath } from '@core/features/tasks/api/browser/utils';
import { formatDiffLineCount } from '@core/primitives/formatting/browser/format-diff-line-count';
import { cn } from '@core/primitives/styling/browser/cn';
import { displayPathForChange } from './changes-tree-utils';

interface ChangesListItemProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  change: GitChange;
  rootPath?: string;
  isSelected?: boolean;
  isActive?: boolean;
  onToggleSelect?: (path: string) => void;
}

export const ChangesListItem = forwardRef<HTMLButtonElement, ChangesListItemProps>(
  ({ change, rootPath, isSelected, isActive, onToggleSelect, className, ...props }, ref) => {
    const displayPath = useMemo(
      () => displayPathForChange(change.path, rootPath),
      [change.path, rootPath]
    );
    const { filename, directory } = useMemo(() => splitPath(displayPath), [displayPath]);
    return (
      <button
        className={cn(
          'group/item w-full flex items-center gap-2 justify-between px-2 py-1 hover:bg-background-1 h-7 rounded-md',
          isActive && 'bg-background-2 hover:bg-background-2',
          className
        )}
        ref={ref}
        {...props}
      >
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <FileIcon filename={filename} size={12} />
          <span className="flex min-w-0 flex-1 items-baseline gap-1.5">
            <span className="max-w-full shrink-0 truncate text-sm">{filename}</span>
            {directory && (
              <span className="min-w-0 shrink truncate text-xs text-foreground-muted">
                {directory}
              </span>
            )}
          </span>
        </div>
        <ChangeStatusAffordance
          change={change}
          filename={filename}
          isSelected={isSelected}
          onToggleSelect={onToggleSelect}
        />
      </button>
    );
  }
);

interface ChangeStatusAffordanceProps {
  change: GitChange;
  filename: string;
  isSelected?: boolean;
  onToggleSelect?: (path: string) => void;
}

export function ChangeStatusAffordance({
  change,
  filename,
  isSelected,
  onToggleSelect,
}: ChangeStatusAffordanceProps) {
  return (
    <div
      className="flex shrink-0 items-center gap-1.5"
      aria-label={`${change.additions} lines added, ${change.deletions} lines removed`}
    >
      <DiffLineStats additions={change.additions} deletions={change.deletions} />
      <span className="relative flex size-4 items-center justify-center">
        <span
          className={cn(
            'transition-opacity',
            onToggleSelect && 'group-hover/item:opacity-0',
            isSelected && 'opacity-0'
          )}
        >
          <GitChangeStatusIcon status={change.status} className="size-4" />
        </span>
        {onToggleSelect && (
          <span
            className={cn(
              'absolute inset-0 flex items-center justify-center transition-opacity',
              'opacity-0 group-hover/item:opacity-100',
              isSelected && 'opacity-100'
            )}
            onClick={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
            onPointerDown={(e) => e.stopPropagation()}
          >
            <Checkbox
              checked={isSelected ?? false}
              onCheckedChange={() => onToggleSelect(change.path)}
              aria-label={`Select ${filename}`}
            />
          </span>
        )}
      </span>
    </div>
  );
}

function DiffLineStats({ additions, deletions }: { additions: number; deletions: number }) {
  if (additions === 0 && deletions === 0) return null;

  return (
    <span className="flex shrink-0 items-center gap-1 text-xs leading-none tabular-nums">
      {additions > 0 && (
        <span className="text-foreground-diff-added">+{formatDiffLineCount(additions)}</span>
      )}
      {deletions > 0 && (
        <span className="text-foreground-diff-deleted">-{formatDiffLineCount(deletions)}</span>
      )}
    </span>
  );
}

export function GitChangeStatusIcon({
  status,
  className,
}: {
  status: GitChangeStatus;
  className?: string;
}) {
  switch (status) {
    case 'added':
      return <SquarePlus className={cn('size-4 text-foreground-diff-added', className)} />;
    case 'modified':
      return <SquareDot className={cn('size-4 text-foreground-diff-modified', className)} />;
    case 'deleted':
      return <SquareMinus className={cn('size-4 text-foreground-diff-deleted', className)} />;
    case 'renamed':
      return <SquareArrowRight className={cn('size-4 text-foreground-muted', className)} />;
    case 'conflicted':
      return <SquareX className={cn('size-4 text-foreground-conflict', className)} />;
    default:
      return null;
  }
}
