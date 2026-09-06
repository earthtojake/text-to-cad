import { and, eq, isNull, ne } from 'drizzle-orm';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import { createWorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import { getProvisionedWorkspaceBranch } from '@core/features/workspaces/api/node/workspace-branch';
import type { DeletePreflightResult, TaskDeletePreflightItem } from '@core/primitives/tasks/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { tasks } from '@core/services/app-db/node/schema';

/**
 * Informed confirmation from the mirror alone (spec §7, planning ticket 09): dirty
 * state, changed lines, unpushed commits, and the observation stamp come straight
 * from the synced registry columns — no host round-trip. Effective Project attachment
 * gates the artifact-deletion option; offline deletion stays desktop-only.
 */
async function getTaskPreflight(
  db: AppDb,
  projects: Pick<ProjectAttachmentManager, 'requireAttached'>,
  taskId: string
): Promise<TaskDeletePreflightItem> {
  const noWorktreeResult: TaskDeletePreflightItem = {
    taskId,
    hasWorktree: false,
    hasUncommittedChanges: false,
    hasDeletableBranch: false,
    hostReachable: true,
  };

  const [task] = await db
    .select()
    .from(tasks)
    .where(and(eq(tasks.id, taskId), isNull(tasks.deletedAt)))
    .limit(1);
  if (!task?.workspaceId) return noWorktreeResult;

  const ws = createWorkspaceRegistry(db).getLive(task.workspaceId);
  if (!ws) return noWorktreeResult;

  const provisionedBranch = getProvisionedWorkspaceBranch(ws);
  if (!provisionedBranch) return noWorktreeResult;

  const siblings = await db
    .select({ id: tasks.id })
    .from(tasks)
    .where(and(eq(tasks.workspaceId, ws.id), ne(tasks.id, taskId), isNull(tasks.deletedAt)))
    .limit(1);

  const hasWorktree = siblings.length === 0;

  // A branch is deletable when it was created from a source branch (create-branch intent).
  const fromBranch = ws.config?.git.kind === 'create-branch' ? ws.config.git.fromBranch : undefined;
  const hasDeletableBranch = hasWorktree && !!fromBranch && provisionedBranch !== fromBranch.branch;

  const observedGit = ws.observedGit ?? null;
  return {
    taskId,
    hasWorktree,
    hasUncommittedChanges: hasWorktree && (observedGit?.dirty ?? false),
    hasDeletableBranch,
    changedLines: observedGit?.diffStats ?? null,
    unpushedCommits: observedGit?.ahead ?? null,
    observedAt: ws.observedAt ?? null,
    hostReachable: projects.requireAttached(task.projectId).success,
  };
}

export async function getDeletePreflight(
  db: AppDb,
  projects: Pick<ProjectAttachmentManager, 'requireAttached'>,
  taskIds: string[]
): Promise<DeletePreflightResult> {
  const items = await Promise.all(taskIds.map((id) => getTaskPreflight(db, projects, id)));
  return { tasks: items };
}
