import { inArray } from 'drizzle-orm';
import type { AppDb, DrizzleTx } from '@core/services/app-db/node/db';
import { projects, tasks } from '@core/services/app-db/node/schema';

export type WorkspaceAnnotationIndex = {
  taskWorkspaceIds: Set<string>;
  projectRepositoryWorkspaceIds: Set<string>;
};

/** The desktop-owned annotation links for a set of mirror rows (task + project-repo). */
export function loadWorkspaceAnnotations(
  db: AppDb | DrizzleTx,
  workspaceIds: string[]
): WorkspaceAnnotationIndex {
  if (workspaceIds.length === 0) {
    return {
      taskWorkspaceIds: new Set<string>(),
      projectRepositoryWorkspaceIds: new Set<string>(),
    };
  }
  const taskRows = db
    .select({ workspaceId: tasks.workspaceId })
    .from(tasks)
    .where(inArray(tasks.workspaceId, workspaceIds))
    .all();
  const projectRows = db
    .select({ workspaceId: projects.repositoryWorkspaceId })
    .from(projects)
    .where(inArray(projects.repositoryWorkspaceId, workspaceIds))
    .all();
  return {
    taskWorkspaceIds: new Set(
      taskRows.flatMap((row) => (row.workspaceId ? [row.workspaceId] : []))
    ),
    projectRepositoryWorkspaceIds: new Set(
      projectRows.flatMap((row) => (row.workspaceId ? [row.workspaceId] : []))
    ),
  };
}
