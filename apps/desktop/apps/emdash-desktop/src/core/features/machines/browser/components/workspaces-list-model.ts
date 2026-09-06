import type { WorkspaceIconStatus, WorkspaceIconType } from '@emdash/ui/react/components';
import { createListView, createTextMatcher, type ListSource } from '@emdash/ui/react/patterns';
import type { WorkspaceRowsGroup } from '@core/features/workspaces/api/browser/use-workspace-rows';
import { aggregateWorkspaceStatus } from '@core/features/workspaces/api/browser/workspace-runtime-status';

/** One row of the workspaces list — a project aggregated across its workspaces. */
export interface WorkspacesListItem {
  id: string;
  name: string;
  path: string;
  kind: Extract<WorkspaceIconType, 'directory' | 'repository'>;
  status: WorkspaceIconStatus;
  worktreeCount: number;
  linkedTaskCount: number;
  /** ISO timestamp of the most recent activity across the project's workspaces. */
  lastActivityAt?: string;
  activeTaskCount: number;
}

/**
 * The list-view state layer for the workspaces list: an externally owned source
 * (the component bridges its query via `useQueryListSource`) plus immediate
 * client-side search over name and path.
 */
export function createWorkspacesListView(source: ListSource<WorkspacesListItem>) {
  return createListView({
    getItemId: (item: WorkspacesListItem) => item.id,
    source,
    search: {
      kind: 'sync',
      predicate: createTextMatcher((item: WorkspacesListItem) => [item.name, item.path]),
    },
  });
}

export type WorkspacesListViewModel = ReturnType<typeof createWorkspacesListView>;

/** Aggregates joined workspace-row groups into one list item per project. */
export function buildWorkspaceItems(groups: readonly WorkspaceRowsGroup[]): WorkspacesListItem[] {
  return groups.map((group) => {
    const rows = group.workspaces;
    const rootRow = rows.find((joined) => joined.row.kind === 'root') ?? rows[0];
    const rowStatuses = rows.map((row) => row.status);

    return {
      id: group.project.id,
      name: group.project.name,
      path: rootRow?.row.path ?? group.project.name,
      kind: 'repository',
      status: aggregateWorkspaceStatus(rowStatuses) satisfies WorkspaceIconStatus,
      worktreeCount: rows.filter((joined) => joined.row.kind !== 'root').length,
      linkedTaskCount: rows.reduce((count, joined) => count + joined.row.tasks.length, 0),
      lastActivityAt: maxTimestamp(rows.map((joined) => joined.row.lastActivityAt)),
      activeTaskCount: rowStatuses.filter((status) => status === 'active').length,
    };
  });
}

function maxTimestamp(values: readonly (string | undefined)[]): string | undefined {
  let latest: string | undefined;
  let latestTime = -Infinity;

  for (const value of values) {
    if (!value) continue;
    const time = Date.parse(value);
    if (Number.isNaN(time) || time <= latestTime) continue;
    latest = value;
    latestTime = time;
  }

  return latest;
}
