import type { HostRef } from '@emdash/core/primitives/host/api';
import { log } from '@emdash/shared/logger';
import { and, desc, eq, isNull } from 'drizzle-orm';
import {
  liveWorkspaces,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import type { Project } from '@core/primitives/projects/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { projects, type ProjectRow } from '@core/services/app-db/node/schema';

/** Host identity + path of a project's repository workspace row. */
export type ProjectRepositoryColumns = {
  path: string | null;
  location: 'local' | 'remote' | null;
  sshConnectionId: string | null;
};

const repositorySelection = {
  project: projects,
  repositoryPath: workspaces.path,
  repositoryLocation: workspaces.location,
  repositorySshConnectionId: workspaces.sshConnectionId,
};

type ProjectJoinRow = {
  project: ProjectRow;
  repositoryPath: string | null;
  repositoryLocation: 'local' | 'remote' | null;
  repositorySshConnectionId: string | null;
};

/**
 * Builds the renderer-facing project from its row plus the repository
 * workspace row that owns the project's path and host identity. Returns null
 * when the repository row is missing or has no path — such a project has no
 * usable identity (the migration train backfills every live project).
 */
export function projectFromRow(
  row: ProjectRow,
  repository: ProjectRepositoryColumns | null
): Project | null {
  if (!repository?.path) return null;
  return repository.location === 'remote'
    ? {
        type: 'ssh',
        id: row.id,
        name: row.name,
        path: repository.path,
        baseRef: row.baseRef,
        connectionId: repository.sshConnectionId ?? '',
        repositoryWorkspaceId: row.repositoryWorkspaceId ?? null,
        createdAt: row.createdAt,
        updatedAt: row.updatedAt,
      }
    : {
        type: 'local',
        id: row.id,
        name: row.name,
        path: repository.path,
        baseRef: row.baseRef,
        repositoryWorkspaceId: row.repositoryWorkspaceId ?? null,
        createdAt: row.createdAt,
        updatedAt: row.updatedAt,
      };
}

function projectFromJoinRow(row: ProjectJoinRow): Project | null {
  const project = projectFromRow(row.project, {
    path: row.repositoryPath,
    location: row.repositoryLocation,
    sshConnectionId: row.repositorySshConnectionId,
  });
  if (!project) {
    log.warn('getProjects: skipping project without a usable repository workspace', {
      projectId: row.project.id,
    });
  }
  return project;
}

export async function getProjects(db: AppDb): Promise<Project[]> {
  const rows = await db
    .select(repositorySelection)
    .from(projects)
    .leftJoin(workspaces, eq(projects.repositoryWorkspaceId, workspaces.id))
    .where(isNull(projects.deletedAt))
    .orderBy(desc(projects.updatedAt));
  return rows.flatMap((row) => {
    const project = projectFromJoinRow(row);
    return project ? [project] : [];
  });
}

export async function getProjectById(db: AppDb, projectId: string): Promise<Project | undefined> {
  const [row] = await db
    .select(repositorySelection)
    .from(projects)
    .leftJoin(workspaces, eq(projects.repositoryWorkspaceId, workspaces.id))
    .where(and(eq(projects.id, projectId), isNull(projects.deletedAt)))
    .limit(1);
  if (!row) return undefined;
  return projectFromJoinRow(row) ?? undefined;
}

export async function getProjectByPath(
  db: AppDb,
  host: HostRef,
  path: string
): Promise<Project | undefined> {
  const [row] = await db
    .select(repositorySelection)
    .from(projects)
    .innerJoin(workspaces, eq(projects.repositoryWorkspaceId, workspaces.id))
    .where(
      and(
        isNull(projects.deletedAt),
        liveWorkspaces(),
        eq(workspaces.path, path),
        host.type === 'local'
          ? eq(workspaces.location, 'local')
          : and(eq(workspaces.location, 'remote'), eq(workspaces.sshConnectionId, host.id))
      )
    )
    .limit(1);
  if (!row) return undefined;
  return projectFromJoinRow(row) ?? undefined;
}
