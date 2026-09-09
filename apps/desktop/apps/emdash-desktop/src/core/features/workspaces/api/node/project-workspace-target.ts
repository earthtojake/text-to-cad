import type { HostRef } from '@emdash/core/primitives/host/api';
import { err, ok, type Result } from '@emdash/shared';
import { and, eq, isNull } from 'drizzle-orm';
import type { AppDb } from '@core/services/app-db/node/db';
import { tasks, type WorkspaceRow } from '@core/services/app-db/node/schema';
import { createWorkspaceRegistry } from './registry';

export type ProjectWorkspaceTargetError = {
  type: 'workspace-unavailable';
  workspaceId: string;
  message: string;
};

export async function resolveProjectWorkspaceTarget(
  db: AppDb,
  project: { id: string; repositoryWorkspaceId: string | null; host: HostRef },
  workspaceId: string
): Promise<Result<WorkspaceRow, ProjectWorkspaceTargetError>> {
  const unavailable = (message: string): Result<WorkspaceRow, ProjectWorkspaceTargetError> =>
    err({ type: 'workspace-unavailable', workspaceId, message });
  const workspace = createWorkspaceRegistry(db).getLive(workspaceId);
  if (!workspace) return unavailable('The selected workspace is no longer registered.');

  const isRepository = workspaceId === project.repositoryWorkspaceId;
  const isChild =
    project.repositoryWorkspaceId !== null && workspace.parentId === project.repositoryWorkspaceId;
  const [linkedTask] = await db
    .select({ id: tasks.id })
    .from(tasks)
    .where(
      and(
        eq(tasks.projectId, project.id),
        eq(tasks.workspaceId, workspaceId),
        isNull(tasks.deletedAt)
      )
    )
    .limit(1);
  if (!isRepository && !isChild && !linkedTask) {
    return unavailable('The selected workspace does not belong to this project.');
  }

  const expectedLocation = project.host.type === 'remote' ? 'remote' : 'local';
  const locationMismatch = workspace.location !== null && workspace.location !== expectedLocation;
  const sshMismatch =
    project.host.type === 'remote'
      ? workspace.sshConnectionId !== null && workspace.sshConnectionId !== project.host.id
      : workspace.sshConnectionId !== null;
  if (locationMismatch || sshMismatch) {
    return unavailable('The selected workspace belongs to a different host.');
  }

  if (!workspace.path?.trim()) return unavailable('The selected workspace has no usable path.');
  if (workspace.observedStatus === 'missing' || workspace.observedGit?.prunable) {
    return unavailable('The selected workspace path is no longer available.');
  }
  if (workspace.deletionTombstone) {
    return unavailable('The selected workspace is being removed.');
  }

  return ok(workspace);
}
