import { and, eq, isNull, type SQL } from 'drizzle-orm';
import {
  liveWorkspaces,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import {
  WorkspaceIdentityService,
  type WorkspaceIdentityRow,
  type WorkspaceIdentitySource,
} from '@core/features/workspaces/api/node/workspace-identity-service';
import type { AppDb } from '@core/services/app-db/node/db';
import { projects, tasks } from '@core/services/app-db/node/schema';

export function createWorkspaceIdentityService(options: { db: AppDb }): WorkspaceIdentityService {
  const source: WorkspaceIdentitySource = {
    async findById(workspaceId) {
      const rows = await loadWorkspaceRows(options.db, eq(workspaces.id, workspaceId));
      return rows[0] ?? null;
    },
    async findRepositoryForProject(projectId) {
      const rows = await options.db
        .select({ workspaceId: projects.repositoryWorkspaceId })
        .from(projects)
        .where(and(eq(projects.id, projectId), isNull(projects.deletedAt)))
        .limit(1);
      const workspaceId = rows[0]?.workspaceId;
      if (!workspaceId) return null;
      const identities = await loadWorkspaceRows(options.db, eq(workspaces.id, workspaceId));
      return identities[0] ?? null;
    },
    async findByPath(path) {
      return loadWorkspaceRows(options.db, eq(workspaces.path, path));
    },
  };
  return new WorkspaceIdentityService(source);
}

async function loadWorkspaceRows(db: AppDb, predicate: SQL): Promise<WorkspaceIdentityRow[]> {
  const rows = await db
    .select({
      workspaceId: workspaces.id,
      type: workspaces.type,
      location: workspaces.location,
      sshConnectionId: workspaces.sshConnectionId,
      path: workspaces.path,
    })
    .from(workspaces)
    .where(and(predicate, liveWorkspaces()));

  const resolved = await Promise.all(
    rows.map(async (row): Promise<WorkspaceIdentityRow | null> => {
      if (!row.path) return null;
      const projectId = await resolveWorkspaceProjectId(db, row.workspaceId);
      if (!projectId) return null;
      return { ...row, path: row.path, projectId };
    })
  );
  return resolved.filter((row): row is WorkspaceIdentityRow => row !== null);
}

async function resolveWorkspaceProjectId(db: AppDb, workspaceId: string): Promise<string | null> {
  const taskRows = await db
    .select({ projectId: tasks.projectId })
    .from(tasks)
    .where(and(eq(tasks.workspaceId, workspaceId), isNull(tasks.deletedAt)))
    .limit(1);
  if (taskRows[0]) return taskRows[0].projectId;

  const projectRows = await db
    .select({ projectId: projects.id })
    .from(projects)
    .where(and(eq(projects.repositoryWorkspaceId, workspaceId), isNull(projects.deletedAt)))
    .limit(1);
  return projectRows[0]?.projectId ?? null;
}
