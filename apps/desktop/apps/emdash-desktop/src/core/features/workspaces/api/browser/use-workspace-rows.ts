import { useMemo } from 'react';
import {
  useProjectWorkspaceUsage,
  useWorkspaceGroups,
  type WorkspacesScope,
} from './use-workspace-groups';
import { joinWorkspaceRows, type JoinedWorkspaceRow } from './workspace-rows';

export type WorkspaceRowsOptions = {
  scope: WorkspacesScope;
  projectId?: string;
  /** Gates on-demand disk usage measurement (needs a reachable host). Rows always render from the mirror. */
  enabled: boolean;
};

const EMPTY_GROUPS: never[] = [];

export function useWorkspaceRows({ scope, projectId, enabled }: WorkspaceRowsOptions) {
  const workspaceQuery = useWorkspaceGroups(scope, true);
  const sourceGroups = workspaceQuery.data ?? EMPTY_GROUPS;
  const sourceGroup = projectId
    ? sourceGroups.find((group) => group.project.id === projectId)
    : undefined;
  const sourceRows = useMemo(
    () =>
      projectId
        ? (sourceGroup?.workspaces ?? [])
        : sourceGroups.flatMap((group) => group.workspaces),
    [projectId, sourceGroup, sourceGroups]
  );
  const measuredPaths = useMemo(
    () => sourceRows.filter((row) => row.pathState === 'measured').map((row) => row.path),
    [sourceRows]
  );
  const usageQuery = useProjectWorkspaceUsage(
    projectId,
    measuredPaths,
    enabled && !!projectId && sourceRows.length > 0
  );
  const joinedRows = useMemo(
    () =>
      joinWorkspaceRows({
        rows: sourceRows,
        usageResults: usageQuery.data?.results,
      }),
    [sourceRows, usageQuery.data?.results]
  );
  const rowsBySource = useMemo(
    () => new Map(joinedRows.map((row) => [sourceKey(row), row])),
    [joinedRows]
  );
  const groups = useMemo(
    () =>
      sourceGroups.map((group) => ({
        project: group.project,
        warnings: group.warnings,
        workspaces: group.workspaces.flatMap((row) => {
          const joined = rowsBySource.get(`${row.projectId}\0${row.workspaceId ?? row.path}`);
          return joined ? [joined] : [];
        }),
      })),
    [rowsBySource, sourceGroups]
  );
  const group = projectId
    ? groups.find((candidate) => candidate.project.id === projectId)
    : undefined;

  return {
    workspaceQuery,
    groups,
    group,
    rows: joinedRows,
    usageQuery,
  };
}

export type WorkspaceRowsResult = ReturnType<typeof useWorkspaceRows>;
export type WorkspaceRowsGroup = WorkspaceRowsResult['groups'][number];

function sourceKey(joined: JoinedWorkspaceRow): string {
  return `${joined.row.projectId}\0${joined.key}`;
}
