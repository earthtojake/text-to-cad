import {
  WorkspaceIcon,
  type WorkspaceIconStatus,
  type WorkspaceIconType,
} from '@emdash/ui/react/components';
import {
  CollectionView,
  CollectionViewCell,
  type CollectionViewColumn,
} from '@emdash/ui/react/patterns';
import { Button, DropdownMenu, RelativeTime, toast, Tooltip } from '@emdash/ui/react/primitives';
import { useQueryClient } from '@tanstack/react-query';
import { BrushCleaningIcon, EllipsisIcon, FolderOpenIcon, Trash2Icon } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useCallback, useId, useMemo, type ReactNode } from 'react';
import type { ProjectHostAccess } from '@core/features/projects/api/browser/stores/project-context';
import { useOpenModal } from '@core/manifests/browser/modal-api';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';
import { formatBytes } from '@core/primitives/formatting/browser/formatBytes';
import type {
  ProjectWorkspaceGitStats,
  ProjectWorkspacePathIssue,
  ProjectWorkspaceRow,
  ProjectWorkspaceUsage,
} from '@core/primitives/workspaces/api';
import { projectWorkspaceOpenInTaskDisabledReason } from '@core/primitives/workspaces/api';
import { getWorkspacesWireClient } from '../../api/browser/client';
import {
  deleteProjectWorkspaces,
  PROJECT_WORKSPACE_USAGE_QUERY_KEY,
  type WorkspacesScope,
} from '../../api/browser/use-workspace-groups';
import { useWorkspaceRows } from '../../api/browser/use-workspace-rows';
import {
  workspaceRowsHostObservation,
  type JoinedWorkspaceRow,
} from '../../api/browser/workspace-rows';
import { aggregateWorkspaceStatus } from '../../api/browser/workspace-runtime-status';
import { GitStatsCell } from './git-stats-cell';
import { WorkspaceRemovalAttentionPanel } from './removal-attention-panel';
import { RepositoryHeader } from './repository-header';
import { PathIssueChip, RemovalPill } from './workspace-pills';
import { workspaceRowLabel } from './workspace-row-label';
import {
  WorkspacesEmptyState,
  WorkspacesErrorState,
  WorkspacesLoadingState,
  WorkspacesOfflineState,
} from './workspace-states';

/** One durable script failure (overlay lifecycle step) or a live overlay notice. */
type WorkspaceScriptIssue = {
  script: string;
  outcome: 'failed' | 'timed-out';
  at: number;
  message?: string;
};

type WorkspaceDetailListItem = {
  id: string;
  name: string;
  path: string;
  iconType: WorkspaceIconType;
  status: WorkspaceIconStatus;
  branch?: string;
  gitStats?: ProjectWorkspaceGitStats;
  usage?: ProjectWorkspaceUsage;
  linkedTaskCount: number;
  activeTaskCount: number;
  loadingGitStats: boolean;
  loadingUsage: boolean;
  pendingRemoval: boolean;
  removalNeedsAttention: boolean;
  statusMessage?: string;
  scriptIssues: WorkspaceScriptIssue[];
  pathIssue?: ProjectWorkspacePathIssue;
  row: ProjectWorkspaceRow;
};

type WorkspaceRowActionHandlers = {
  onOpenInTask: (item: WorkspaceDetailListItem) => void;
  onCleanArtifacts: (item: WorkspaceDetailListItem) => void;
  onDelete: (item: WorkspaceDetailListItem) => void;
};

function buildDetailColumns(
  handlers: WorkspaceRowActionHandlers,
  hostActionDisabledReason?: string
): CollectionViewColumn<WorkspaceDetailListItem>[] {
  return [
    ...DETAIL_COLUMNS,
    {
      id: 'actions',
      width: '2.5rem',
      cell: (item) => (
        <RowActionsMenu
          item={item}
          handlers={handlers}
          hostActionDisabledReason={hostActionDisabledReason}
        />
      ),
    },
  ];
}

const DETAIL_COLUMNS: CollectionViewColumn<WorkspaceDetailListItem>[] = [
  {
    id: 'icon',
    width: '2.25rem',
    cell: (item) => <WorkspaceIcon type={item.iconType} status={item.status} />,
  },
  {
    id: 'name',
    width: 'minmax(0, 1fr)',
    cell: (item) => (
      <CollectionViewCell
        primary={
          <span className="inline-flex min-w-0 items-center gap-2">
            <span className="truncate">{item.name}</span>
            {item.pathIssue && <PathIssueChip issue={item.pathIssue} path={item.path} />}
            <RemovalPill
              pendingRemoval={item.pendingRemoval}
              needsAttention={item.removalNeedsAttention}
              message={item.statusMessage}
            />
            {item.scriptIssues.map((issue) => (
              <ScriptIssueChip key={issue.script} issue={issue} />
            ))}
          </span>
        }
        secondary={item.path}
      />
    ),
  },
  {
    id: 'git',
    width: '13rem',
    cell: (item) => (
      <CollectionViewCell
        primary={item.branch ?? 'No branch'}
        secondary={<GitStatsCell stats={item.gitStats} loading={item.loadingGitStats} />}
      />
    ),
  },
  {
    id: 'storage',
    width: '9rem',
    cell: (item) => (
      <CollectionViewCell
        primary={
          item.usage ? formatBytes(item.usage.totalBytes) : item.loadingUsage ? 'Loading...' : '-'
        }
        secondary={
          item.usage
            ? `${formatBytes(item.usage.artifactBytes)} artifacts`
            : item.loadingUsage
              ? 'Scanning artifacts'
              : '-'
        }
      />
    ),
  },
  {
    id: 'tasks',
    width: '10rem',
    cell: (item) => (
      <CollectionViewCell
        primary={formatCount(item.linkedTaskCount, 'Linked task')}
        secondary={formatCount(item.activeTaskCount, 'task active', 'tasks active')}
      />
    ),
  },
];

/**
 * Scope-aware project workspace detail, shared by the settings pages and the
 * project view. The machine-scoped settings wrapper lives in the machines slice,
 * which owns the connection-state lookup.
 */
export const WorkspaceDetailPage = observer(function WorkspaceDetailPage({
  scope,
  host,
  machineName,
  projectId,
  onDeletedAll,
}: {
  scope: WorkspacesScope;
  host?: ProjectHostAccess;
  machineName?: string;
  projectId: string;
  /** Called after a full successful project-wide delete; settings hosts navigate back, the project tab stays. */
  onDeletedAll?: () => void;
}) {
  const openConfirm = useOpenModal('confirmActionModal');
  const openTask = useOpenModal('taskModal');
  const queryClient = useQueryClient();
  const liveActionsEnabled = host?.liveAction.kind === 'enabled';
  const hostActionDisabledReason = liveActionsEnabled
    ? undefined
    : projectAvailabilityUi.defaultLiveActionDisabledReason;
  const workspaceRows = useWorkspaceRows({ scope, projectId, enabled: liveActionsEnabled });
  const { workspaceQuery, group, rows, usageQuery } = workspaceRows;
  const observation =
    host?.observe(workspaceRowsHostObservation(rows)) ?? ({ kind: 'unavailable' } as const);
  const rowStatuses = rows.map((row) => row.status);
  const aggregateStatus = aggregateWorkspaceStatus(rowStatuses) satisfies WorkspaceIconStatus;
  const rootJoined = rows.find((joined) => joined.row.kind === 'root') ?? rows[0];
  const rootRow = rootJoined?.row;
  const worktreeItems = rows
    .filter((row) => row !== rootJoined)
    .map((joined) =>
      buildWorktreeItem({
        joined,
        loadingUsage: usageQuery.isLoading || usageQuery.isFetching,
      })
    );

  const handleDelete = useCallback(async () => {
    if (!group) return;
    // Tombstoned rows already fold into `canDelete: false` — no second delete.
    const deletableRows = group.workspaces.filter((row) => row.row.canDelete);
    if (deletableRows.length === 0) {
      const pendingCount = group.workspaces.filter((row) => row.pendingRemoval).length;
      toast(pendingCount > 0 ? 'Removal already pending' : 'No deletable workspaces', {
        description:
          pendingCount > 0
            ? 'These workspaces are already being removed.'
            : 'Repository roots cannot be deleted from this view.',
      });
      return;
    }

    const outcome = await openConfirm({
      title: `Delete ${group.project.name} workspaces?`,
      description:
        'This deletes linked task worktrees for this repository where supported. Repository roots are preserved.',
      confirmLabel: 'Delete',
      variant: 'destructive',
      // Unchecked default (spec §7.1): removal keeps conversation records.
      checkbox: { label: 'Delete their conversations too' },
    });

    if (!outcome.success) return;

    try {
      const result = await deleteProjectWorkspaces({
        projectId: group.project.id,
        paths: deletableRows.map((row) => row.row.path),
        deleteConversations: outcome.data?.checked ?? false,
      });
      const failed = result.results.filter((row) => !row.success);

      if (failed.length > 0) {
        toast.error(`${result.results.length - failed.length} deleted, ${failed.length} failed`, {
          description: failed[0]?.message,
        });
      } else {
        toast(`Deleted ${deletableRows.length} workspaces`);
        onDeletedAll?.();
      }
      // No cache invalidation: the mirror live model streams the deletions.
    } catch (error) {
      toast.error('Could not delete workspaces', {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  }, [group, onDeletedAll, openConfirm]);

  const refreshUsage = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: [PROJECT_WORKSPACE_USAGE_QUERY_KEY, projectId],
    });
  }, [projectId, queryClient]);

  const handleOpenInTask = useCallback(
    (item: WorkspaceDetailListItem) => {
      const workspaceId = item.row.workspaceId;
      if (!workspaceId) return;
      void openTask({ projectId: item.row.projectId, initialWorkspaceId: workspaceId });
    },
    [openTask]
  );

  const handleCleanArtifacts = useCallback(
    async (item: WorkspaceDetailListItem) => {
      const { row } = item;
      const outcome = await openConfirm({
        title: `Clean artifacts for ${item.name}?`,
        description: row.hasActiveSessions
          ? 'This stops active sessions, runs teardown scripts, and removes gitignored artifacts. Tasks remain restorable, but dependencies may need to be restored.'
          : 'This runs teardown scripts and removes gitignored dependencies, build output, and caches. The worktree and its tasks stay intact.',
        confirmLabel: 'Clean Artifacts',
      });
      if (!outcome.success) return;

      try {
        const client = await getWorkspacesWireClient();
        const result = await client.archive({
          projectId: row.projectId,
          workspaceId: row.workspaceId ?? undefined,
          workspacePath: row.path,
          branchName: row.branch,
        });
        if (result.success) {
          toast(`Queued artifact cleanup for ${item.name}`);
        } else {
          toast.error('Could not clean artifacts', { description: result.error.message });
        }
      } catch (error) {
        toast.error('Could not clean artifacts', {
          description: error instanceof Error ? error.message : String(error),
        });
      }
      refreshUsage();
    },
    [openConfirm, refreshUsage]
  );

  const handleDeleteRow = useCallback(
    async (item: WorkspaceDetailListItem) => {
      const { row } = item;
      const outcome = await openConfirm({
        title: `Delete ${item.name}?`,
        description: row.hasActiveSessions
          ? 'This removes the workspace and its linked tasks. Active sessions will be stopped.'
          : 'This removes the workspace. Linked tasks are deleted with their owned worktrees.',
        confirmLabel: 'Delete',
        variant: 'destructive',
        // Unchecked default (spec §7.1): removal keeps conversation records.
        checkbox: { label: 'Delete their conversations too' },
      });
      if (!outcome.success) return;

      try {
        const result = await deleteProjectWorkspaces({
          projectId: row.projectId,
          paths: [row.path],
          deleteConversations: outcome.data?.checked ?? false,
        });
        const failure = result.results.find((entry) => !entry.success);
        if (failure && !failure.success) {
          toast.error('Could not delete workspace', { description: failure.message });
        } else {
          toast(`Deleted ${item.name}`);
        }
        // No cache invalidation for rows: the mirror live model streams the deletion.
      } catch (error) {
        toast.error('Could not delete workspace', {
          description: error instanceof Error ? error.message : String(error),
        });
      }
      refreshUsage();
    },
    [openConfirm, refreshUsage]
  );

  const columns = useMemo(
    () =>
      buildDetailColumns(
        {
          onOpenInTask: handleOpenInTask,
          onCleanArtifacts: (item) => void handleCleanArtifacts(item),
          onDelete: (item) => void handleDeleteRow(item),
        },
        hostActionDisabledReason
      ),
    [handleCleanArtifacts, handleDeleteRow, handleOpenInTask, hostActionDisabledReason]
  );

  if (workspaceQuery.isLoading && liveActionsEnabled) {
    return <WorkspacesLoadingState label="Loading workspace" />;
  }
  if (workspaceQuery.isError && observation.kind === 'unavailable') {
    return <WorkspacesErrorState error={workspaceQuery.error} title="Could not load workspace." />;
  }
  if (observation.kind === 'unavailable') {
    return (
      <WorkspacesOfflineState
        title={liveActionsEnabled ? 'Workspace data unavailable' : undefined}
        description={
          liveActionsEnabled
            ? scope.kind === 'local'
              ? 'Workspace data has not been loaded from the Local runtime yet.'
              : `${machineName?.trim() || 'This Machine'} has not provided workspace data yet.`
            : machineName
              ? `${machineName} has not provided a workspace observation yet.`
              : 'Workspace data will appear after live Project access returns.'
        }
      />
    );
  }
  if (!group || !rootJoined || !rootRow) {
    return <WorkspacesEmptyState message="Workspace not found." />;
  }

  return (
    <Tooltip.Provider delay={150}>
      <div className="flex min-h-0 flex-col gap-6 pb-4">
        {observation.kind === 'stale' && (
          <div
            role="status"
            className="rounded-md border border-border-warning bg-background-warning px-3 py-2 text-xs text-foreground-warning"
          >
            Showing the last observed workspace data.{' '}
            {projectAvailabilityUi.defaultLiveActionDisabledReason}
          </div>
        )}
        <RepositoryHeader
          project={group.project}
          rootRow={rootRow}
          rows={rows.map((joined) => joined.row)}
          status={aggregateStatus}
          usage={rootJoined.usage}
          gitStats={rootJoined.gitStats}
          loadingUsage={
            (usageQuery.isLoading || usageQuery.isFetching) && rootRow.pathState === 'measured'
          }
          loadingGitStats={false}
          warnings={group.warnings}
          onDelete={() => void handleDelete()}
          actionDisabledReason={hostActionDisabledReason}
        />

        <WorkspaceRemovalAttentionPanel rows={rows.map((joined) => joined.row)} />

        <WorkspaceSection label="Worktrees">
          <CollectionView
            items={worktreeItems}
            columns={columns}
            getItemKey={(item) => item.id}
            emptySlot={<WorkspacesEmptyState message="No worktrees found." className="h-32" />}
          />
        </WorkspaceSection>
      </div>
    </Tooltip.Provider>
  );
});

function WorkspaceSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="flex min-h-0 flex-col gap-2">
      <div className="px-1 text-xs font-medium tracking-wide text-foreground-muted uppercase">
        {label}
      </div>
      {children}
    </section>
  );
}

function buildWorktreeItem({
  joined,
  loadingUsage,
}: {
  joined: JoinedWorkspaceRow;
  loadingUsage: boolean;
}): WorkspaceDetailListItem {
  const { row } = joined;
  return {
    id: joined.key,
    name: workspaceRowLabel(row),
    path: row.path,
    iconType: 'worktree',
    status: joined.status satisfies WorkspaceIconStatus,
    branch: row.branch,
    gitStats: joined.gitStats,
    usage: joined.usage,
    linkedTaskCount: row.tasks.length,
    activeTaskCount: activeTaskCount(row),
    loadingUsage: loadingUsage && row.pathState === 'measured',
    loadingGitStats: false,
    pendingRemoval: joined.pendingRemoval,
    removalNeedsAttention: joined.removalNeedsAttention,
    statusMessage: joined.statusMessage,
    scriptIssues: workspaceScriptIssues(row),
    ...(row.pathIssue ? { pathIssue: row.pathIssue } : {}),
    row,
  };
}

function RowActionsMenu({
  item,
  handlers,
  hostActionDisabledReason,
}: {
  item: WorkspaceDetailListItem;
  handlers: WorkspaceRowActionHandlers;
  hostActionDisabledReason?: string;
}) {
  const disabledReasonId = useId();
  const { canCleanArtifacts, canDelete } = item.row;
  const openInTaskDisabledReason = projectWorkspaceOpenInTaskDisabledReason(item.row);
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="xs"
            icon
            aria-label={`Actions for ${item.name}`}
          >
            <EllipsisIcon aria-hidden />
          </Button>
        }
      />
      <DropdownMenu.Content align="end">
        <DropdownMenu.Item
          disabled={!!openInTaskDisabledReason || !!hostActionDisabledReason}
          aria-describedby={hostActionDisabledReason ? disabledReasonId : undefined}
          title={openInTaskDisabledReason}
          onClick={() => handlers.onOpenInTask(item)}
        >
          <FolderOpenIcon aria-hidden />
          Open in Task
        </DropdownMenu.Item>
        <DropdownMenu.Separator />
        <DropdownMenu.Item
          disabled={!canCleanArtifacts || !!hostActionDisabledReason}
          aria-describedby={hostActionDisabledReason ? disabledReasonId : undefined}
          onClick={() => handlers.onCleanArtifacts(item)}
        >
          <BrushCleaningIcon aria-hidden />
          Clean Artifacts
        </DropdownMenu.Item>
        <DropdownMenu.Separator />
        <DropdownMenu.Item
          variant="destructive"
          disabled={!canDelete || !!hostActionDisabledReason}
          aria-describedby={hostActionDisabledReason ? disabledReasonId : undefined}
          onClick={() => handlers.onDelete(item)}
        >
          <Trash2Icon aria-hidden />
          Delete
        </DropdownMenu.Item>
        {hostActionDisabledReason && (
          <span id={disabledReasonId} className="sr-only">
            {hostActionDisabledReason}
          </span>
        )}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}

/**
 * One chip per script: the durable lifecycle step (mirror overlay, survives daemon
 * restarts) is the fact of record; a live overlay notice only adds a chip for a
 * script without a durable failure yet — never a duplicate of the same failure.
 */
function workspaceScriptIssues(row: ProjectWorkspaceRow): WorkspaceScriptIssue[] {
  const issues: WorkspaceScriptIssue[] = [];
  for (const script of ['prepare', 'setup', 'run'] as const) {
    const step = row.runtimeOverlay?.lifecycle?.find((entry) => entry.id === script);
    if (step && step.status === 'failed') {
      issues.push({
        script,
        outcome: 'failed',
        at: step.finishedAt ?? step.startedAt ?? 0,
        message: step.message,
      });
    }
  }
  const covered = new Set(issues.map((issue) => issue.script));
  for (const notice of row.runtimeOverlay?.notices ?? []) {
    if (notice.kind !== 'script-failed' || covered.has(notice.script)) continue;
    covered.add(notice.script);
    issues.push({
      script: notice.script,
      outcome: 'failed',
      at: notice.at,
      message: notice.message,
    });
  }
  return issues;
}

function ScriptIssueChip({ issue }: { issue: WorkspaceScriptIssue }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger>
        <span className="shrink-0 rounded-full border border-border-warning px-1.5 py-0.5 text-micro tracking-wide text-foreground-warning uppercase">
          {scriptIssueLabel(issue)}
        </span>
      </Tooltip.Trigger>
      <Tooltip.Content className="max-w-80 text-xs">
        {scriptIssueLabel(issue)} <RelativeTime value={issue.at} />
        {issue.message ? `: ${issue.message}` : ''}
      </Tooltip.Content>
    </Tooltip.Root>
  );
}

function scriptIssueLabel(issue: WorkspaceScriptIssue): string {
  const script = issue.script[0]!.toUpperCase() + issue.script.slice(1);
  return `${script} ${issue.outcome === 'timed-out' ? 'timed out' : 'failed'}`;
}

function activeTaskCount(row: ProjectWorkspaceRow): number {
  return row.tasks.filter((task) => task.status === 'in_progress' || task.status === 'review')
    .length;
}

function formatCount(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}
