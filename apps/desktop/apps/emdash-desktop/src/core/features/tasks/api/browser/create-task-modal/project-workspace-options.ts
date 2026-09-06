import {
  projectWorkspaceOpenInTaskDisabledReason,
  type ProjectWorkspaceRow,
} from '@core/primitives/workspaces/api';

export type ProjectWorkspaceOption = {
  key: string;
  workspaceId: string | null;
  kind: 'repository' | 'worktree';
  path: string;
  branchName: string | null;
  linesAdded: number | null;
  linesDeleted: number | null;
  taskName: string | null;
  isLive: boolean;
  linkedTaskCount: number;
  disabledReason?: string;
};

export function projectWorkspaceOption(row: ProjectWorkspaceRow): ProjectWorkspaceOption {
  const preferredTask = row.tasks.find((task) => !task.archivedAt) ?? row.tasks[0];
  const disabledReason = projectWorkspaceOpenInTaskDisabledReason(row);
  return {
    key: `${row.projectId}\0${row.workspaceId ?? row.path}`,
    workspaceId: row.workspaceId,
    kind: row.kind === 'root' ? 'repository' : 'worktree',
    path: row.path,
    branchName: row.branch ?? null,
    linesAdded: row.gitStats?.added ?? null,
    linesDeleted: row.gitStats?.removed ?? null,
    taskName: preferredTask?.name ?? null,
    isLive: row.hasActiveSessions,
    linkedTaskCount: row.tasks.length,
    ...(disabledReason ? { disabledReason } : {}),
  };
}
