import { Button, RelativeTime, Spinner, toast } from '@emdash/ui/react/primitives';
import { AlertTriangleIcon } from 'lucide-react';
import { useState } from 'react';
import { getWorkspaceRegistryWireClient } from '@core/features/workspaces/api/browser/client';
import { cn } from '@core/primitives/styling/browser/cn';
import {
  workspaceRemovalNeedsAttention,
  type ProjectWorkspaceRow,
} from '@core/primitives/workspaces/api';
import { workspaceRowLabel } from './workspace-row-label';

type RemovalAction = 'retry' | 'untrack';

type AttentionRow = ProjectWorkspaceRow & { workspaceId: string };

function needsRemovalAttention(row: ProjectWorkspaceRow): row is AttentionRow {
  return row.workspaceId !== null && workspaceRemovalNeedsAttention(row);
}

/**
 * Needs-attention cards for pending deletions stopped by a terminal removal failure
 * (ADR 0006): one card per tombstoned row carrying an active durable `removalStop`,
 * with the Retry and Untrack-anyway affordances wired to the workspace registry verbs.
 * Renders nothing while every removal is converging on its own.
 */
export function WorkspaceRemovalAttentionPanel({
  rows,
  className,
}: {
  rows: readonly ProjectWorkspaceRow[];
  className?: string;
}) {
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const attentionRows = rows.filter(needsRemovalAttention);
  if (attentionRows.length === 0) return null;

  const runAction = async (action: RemovalAction, workspaceId: string): Promise<void> => {
    setPendingAction(`${action}:${workspaceId}`);
    try {
      const registry = await getWorkspaceRegistryWireClient();
      if (action === 'retry') {
        await registry.retryWorkspaceRemoval({ workspaceId });
        toast('Removal retrying', { description: 'The removal runs again in the background.' });
      } else {
        await registry.abandonWorkspaceRemoval({ workspaceId });
        toast('Workspace untracked', {
          description: 'Hardcore dropped the pending removal without deleting files on the host.',
        });
      }
    } catch (error) {
      toast.error(action === 'retry' ? 'Could not retry removal' : 'Could not untrack workspace', {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {attentionRows.map((row) => (
        <div
          key={row.workspaceId}
          className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border-destructive bg-background-secondary/40 px-3 py-2"
        >
          <div className="flex min-w-0 items-start gap-2">
            <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0 text-foreground-destructive" />
            <div className="min-w-0 text-xs">
              <div className="font-medium text-foreground">
                Couldn't remove {workspaceRowLabel(row)}
              </div>
              <div className="truncate text-foreground-muted">
                {row.removalStop && (
                  <>
                    {row.removalStop.message}
                    {' · '}
                    <RelativeTime value={row.removalStop.at} />
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <RemovalActionButton
              label="Retry"
              pending={pendingAction === `retry:${row.workspaceId}`}
              disabled={pendingAction !== null}
              onClick={() => void runAction('retry', row.workspaceId)}
            />
            <RemovalActionButton
              label="Untrack anyway"
              pending={pendingAction === `untrack:${row.workspaceId}`}
              disabled={pendingAction !== null}
              onClick={() => void runAction('untrack', row.workspaceId)}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function RemovalActionButton({
  label,
  pending,
  disabled,
  onClick,
}: {
  label: string;
  pending: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <Button variant="secondary" size="sm" disabled={disabled} onClick={onClick}>
      {pending && <Spinner size="sm" />}
      {label}
    </Button>
  );
}
