import { type ReactNode } from 'react';

interface ActionCardProps {
  selectedCount: number;
  selectionActions: ReactNode;
  generalActions: ReactNode;
}

export function ActionCard({ selectedCount, selectionActions, generalActions }: ActionCardProps) {
  const hasSelection = selectedCount > 0;
  return (
    <div className="mx-2 flex shrink-0 items-center justify-between rounded-lg border border-border bg-background-1 py-1.5 pr-1.5 pl-2.5">
      <span className="min-w-0 truncate text-xs text-foreground-muted">
        {hasSelection
          ? `${selectedCount} file${selectedCount !== 1 ? 's' : ''} selected`
          : 'All files'}
      </span>
      <div className="flex items-center gap-1.5">
        {hasSelection ? selectionActions : generalActions}
      </div>
    </div>
  );
}
