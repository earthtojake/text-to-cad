import { Spinner } from '@emdash/ui/react/primitives';
import { WifiOffIcon } from 'lucide-react';
import { cn } from '@core/primitives/styling/browser/cn';

export function WorkspacesLoadingState({ label = 'Loading workspaces' }: { label?: string }) {
  return (
    <div className="flex h-40 items-center justify-center gap-2 text-sm text-foreground-muted">
      <Spinner size="sm" />
      {label}
    </div>
  );
}

export function WorkspacesErrorState({
  error,
  title = 'Could not load workspaces.',
}: {
  error: unknown;
  title?: string;
}) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="flex h-40 flex-col items-center justify-center gap-1 text-sm">
      <div className="text-foreground-destructive">{title}</div>
      <div className="max-w-md text-center text-xs text-foreground-muted">{message}</div>
    </div>
  );
}

export function WorkspacesEmptyState({
  message,
  className,
}: {
  message: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex h-40 items-center justify-center text-sm text-foreground-muted',
        className
      )}
    >
      {message}
    </div>
  );
}

export function WorkspacesOfflineState({
  title = 'Machine offline',
  description,
}: {
  title?: string;
  description: string;
}) {
  return (
    <div className="flex h-40 flex-col items-center justify-center gap-1 text-sm text-foreground-muted">
      <div className="inline-flex items-center gap-2">
        <WifiOffIcon className="size-4" />
        {title}
      </div>
      <p className="max-w-sm text-center text-xs text-foreground-passive">{description}</p>
    </div>
  );
}
