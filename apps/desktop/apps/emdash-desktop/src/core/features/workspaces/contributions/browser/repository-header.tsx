import { WorkspaceIcon, type WorkspaceIconStatus } from '@emdash/ui/react/components';
import { Button, DropdownMenu } from '@emdash/ui/react/primitives';
import { AlertTriangleIcon, EllipsisIcon, Trash2Icon } from 'lucide-react';
import { useId } from 'react';
import { formatBytes } from '@core/primitives/formatting/browser/formatBytes';
import type {
  ProjectWorkspaceGitStats,
  ProjectWorkspaceRow,
  ProjectWorkspaceUsage,
} from '@core/primitives/workspaces/api';
import { GitStatsCell } from './git-stats-cell';
import { PathIssueSummaryPill, RemovalSummaryPill } from './workspace-pills';

export function RepositoryHeader({
  project,
  rootRow,
  rows,
  status,
  usage,
  gitStats,
  loadingUsage,
  loadingGitStats,
  warnings,
  onDelete,
  actionDisabledReason,
}: {
  project: { id: string; name: string };
  rootRow: ProjectWorkspaceRow;
  rows: readonly ProjectWorkspaceRow[];
  status: WorkspaceIconStatus;
  usage: ProjectWorkspaceUsage | undefined;
  gitStats: ProjectWorkspaceGitStats | undefined;
  loadingUsage: boolean;
  loadingGitStats: boolean;
  warnings: readonly string[];
  onDelete(): void;
  actionDisabledReason?: string;
}) {
  const healthStatus = status;
  const disabledReasonId = useId();

  return (
    <section className="rounded-lg border border-border bg-background-secondary/40 px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <WorkspaceIcon type="repository" status={healthStatus} size="2.75rem" />
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <h2 className="truncate text-base font-semibold text-foreground">{project.name}</h2>
              {healthStatus !== 'idle' && (
                <span className={runtimeStatusPillClass(healthStatus)}>
                  {runtimeStatusLabel(healthStatus)}
                </span>
              )}
              <PathIssueSummaryPill rows={rows} className="px-2" />
              <RemovalSummaryPill rows={rows} className="px-2" />
            </div>
            <div className="mt-0.5 truncate text-xs text-foreground-muted">{rootRow.path}</div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-foreground-muted">
              <span>{rootRow.branch ?? 'No branch'}</span>
              <span>
                <GitStatsCell stats={gitStats} loading={loadingGitStats} />
              </span>
              <span>{usageLabel(usage, loadingUsage)}</span>
              {usage && <span>{formatBytes(usage.artifactBytes)} artifacts</span>}
              <span>{syncLabel(rootRow.lastObservedAt)}</span>
            </div>
          </div>
        </div>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger
            render={
              <Button type="button" variant="ghost" size="xs" icon aria-label="Workspace actions">
                <EllipsisIcon aria-hidden />
              </Button>
            }
          />
          <DropdownMenu.Content align="end">
            <DropdownMenu.Item
              variant="destructive"
              disabled={!!actionDisabledReason}
              aria-describedby={actionDisabledReason ? disabledReasonId : undefined}
              onClick={onDelete}
            >
              <Trash2Icon aria-hidden />
              Delete
            </DropdownMenu.Item>
            {actionDisabledReason && (
              <span id={disabledReasonId} className="sr-only">
                {actionDisabledReason}
              </span>
            )}
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </div>
      <WorkspaceScanWarnings warnings={warnings} />
    </section>
  );
}

function usageLabel(usage: ProjectWorkspaceUsage | undefined, loading: boolean): string {
  if (usage) return formatBytes(usage.totalBytes);
  return loading ? 'Loading usage...' : 'Usage unavailable';
}

function syncLabel(lastObservedAt: string | undefined): string {
  if (!lastObservedAt) return 'Not synced yet';
  const timestamp = Date.parse(lastObservedAt);
  if (!Number.isFinite(timestamp)) return 'Sync time unknown';
  const elapsedMs = Math.max(0, Date.now() - timestamp);
  const minutes = Math.floor(elapsedMs / 60_000);
  if (minutes < 1) return 'Synced just now';
  if (minutes < 60) return `Synced ${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Synced ${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `Synced ${days}d ago`;
}

function runtimeStatusLabel(status: WorkspaceIconStatus): string {
  switch (status) {
    case 'active':
      return 'Active';
    case 'setting-up':
      return 'Setting up';
    case 'tearing-down':
      return 'Tearing down';
    case 'error':
      return 'Error';
    case 'idle':
      return 'Idle';
  }
}

function WorkspaceScanWarnings({ warnings }: { warnings: readonly string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="mt-3 flex items-start gap-2 rounded-md border border-border-warning bg-background-warning px-3 py-2 text-xs text-foreground-warning">
      <AlertTriangleIcon className="mt-0.5 size-3.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="font-medium">Workspace scan completed with warnings</div>
        <div className="truncate text-foreground-warning/80">{warnings.join(' ')}</div>
      </div>
    </div>
  );
}

function runtimeStatusPillClass(status: WorkspaceIconStatus): string {
  const base = 'rounded-full border px-2 py-0.5 text-micro tracking-wide uppercase';
  switch (status) {
    case 'active':
      return `${base} border-border-success text-foreground-success`;
    case 'setting-up':
      return `${base} border-border-info text-foreground-info`;
    case 'tearing-down':
      return `${base} border-border-warning text-foreground-warning`;
    case 'error':
      return `${base} border-border-destructive text-foreground-destructive`;
    case 'idle':
      return base;
  }
}
