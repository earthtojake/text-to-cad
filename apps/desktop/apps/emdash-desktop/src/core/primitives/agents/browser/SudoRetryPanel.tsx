import { formatCommandOutputTail } from '@emdash/core/primitives/host-dependencies/api';
import type { PermissionDeniedError } from '@emdash/core/primitives/host-dependencies/api';
import { Loader2, TriangleAlert, X } from 'lucide-react';
import { useState } from 'react';
import { cn } from '@core/primitives/styling/browser/cn';
import { CommandActionButton, CommandRow } from './install-command-row';

export type SudoRetryPanelProps = {
  error: PermissionDeniedError;
  dependencyName: string;
  isRetrying: boolean;
  onRetry: () => void;
  onDismiss?: () => void;
  compact?: boolean;
};

export function SudoRetryPanel({
  error,
  dependencyName,
  isRetrying,
  onRetry,
  onDismiss,
  compact = false,
}: SudoRetryPanelProps) {
  const [showOutput, setShowOutput] = useState(false);
  const output = formatCommandOutputTail(error.output ?? '');
  const command = error.canRetryWithSudo
    ? error.elevatedCommand
    : (error.interactiveCommand ?? error.command);

  return (
    <div
      className={cn(
        'space-y-2 rounded-lg border border-foreground-warning/30 bg-background-warning/30 p-3',
        compact && 'p-2.5'
      )}
      role="alert"
    >
      <div className="flex items-center gap-2 text-sm">
        <TriangleAlert className="h-4 w-4 shrink-0 text-foreground-warning" />
        <span className="font-medium">Permission denied</span>
        {onDismiss ? (
          <button
            type="button"
            aria-label="Dismiss permission error"
            className="ml-auto rounded p-0.5 text-foreground-passive hover:bg-background-2 hover:text-foreground"
            onClick={onDismiss}
          >
            <X className="size-3.5" />
          </button>
        ) : null}
      </div>

      {error.canRetryWithSudo ? (
        <p className="text-xs text-foreground-muted">
          The command needs elevated permissions. You can retry with administrator privileges.
        </p>
      ) : (
        <p className="text-xs text-foreground-muted">
          Installing {dependencyName} needs elevated permissions and passwordless sudo isn't
          available on this host. Run this command in a terminal on this machine.
        </p>
      )}

      {command ? (
        <CommandRow
          command={command}
          action={
            error.canRetryWithSudo ? (
              <CommandActionButton disabled={isRetrying} onClick={onRetry}>
                {isRetrying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Retry with sudo'}
              </CommandActionButton>
            ) : null
          }
        />
      ) : null}

      {output ? (
        <>
          <button
            type="button"
            onClick={() => setShowOutput((visible) => !visible)}
            className="text-xs text-foreground-passive hover:text-foreground"
          >
            {showOutput ? 'Hide output' : 'Show output'}
          </button>
          {showOutput ? (
            <pre className="max-h-40 overflow-auto rounded bg-background-quaternary-1 p-2 font-mono text-tiny whitespace-pre-wrap text-foreground-muted">
              {output}
            </pre>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
