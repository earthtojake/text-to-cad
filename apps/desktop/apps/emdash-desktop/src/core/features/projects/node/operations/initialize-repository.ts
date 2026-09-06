import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { err, ok } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import { and, eq, isNull, sql } from 'drizzle-orm';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import { createWorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import { translateWorkspaceIdentity } from '@core/features/workspaces/api/node/translate-workspace-identity';
import { workspaceHostStorage } from '@core/features/workspaces/api/node/workspace-identity-service';
import { projectHostRef } from '@core/primitives/projects/api';
import type { InitializeRepositoryResult } from '@core/primitives/projects/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { projects } from '@core/services/app-db/node/schema';
import { ensureProjectRepository } from './create-project-utils';
import { getProjectById } from './getProjects';

export type InitializeRepositoryDependencies = {
  db: AppDb;
  runtimes: Pick<RuntimeBroker, 'client'>;
  projects: Pick<ProjectAttachmentManager, 'invalidate'>;
};

export async function initializeRepository(
  dependencies: InitializeRepositoryDependencies,
  projectId: string
): Promise<InitializeRepositoryResult> {
  const existingProject = await getProjectById(dependencies.db, projectId);
  if (!existingProject) {
    return err({
      type: 'project-not-found',
      projectId,
      message: `Project ${projectId} not found`,
    });
  }

  const host = projectHostRef(existingProject);
  const runtime = await dependencies.runtimes.client(host);
  if (!runtime.success) return err(runtime.error);

  const repositoryResult = await ensureProjectRepository(
    runtime.data.git,
    existingProject.path,
    true
  );
  if (!repositoryResult.success) return repositoryResult;

  if (existingProject.repositoryWorkspaceId) {
    const registered = await runtime.data.workspaceRegistry.createWorkspace({
      workspaceId: existingProject.repositoryWorkspaceId,
      path: repositoryResult.data.rootPath,
    });
    if (!registered.success) {
      return err({
        type: 'open-repository-failed',
        path: repositoryResult.data.rootPath,
        message: `Could not refresh the Host workspace (${registered.error.type})`,
      });
    }
    const storage = workspaceHostStorage(host);
    const claim = {
      host: { location: storage.location, sshConnectionId: storage.sshConnectionId },
      record: registered.data,
    } as const;
    const claimed =
      registered.data.id === existingProject.repositoryWorkspaceId
        ? createWorkspaceRegistry(dependencies.db).claim(claim)
        : translateWorkspaceIdentity(
            dependencies.db,
            existingProject.repositoryWorkspaceId,
            claim,
            existingProject.path
          );
    if (!claimed.success) {
      return err({
        type: 'open-repository-failed',
        path: repositoryResult.data.rootPath,
        message: `Could not bind the canonical Host workspace (${claimed.error.type})`,
      });
    }
  }

  await dependencies.db
    .update(projects)
    .set({
      baseRef: repositoryResult.data.baseRef,
      updatedAt: sql`CURRENT_TIMESTAMP`,
    })
    .where(and(eq(projects.id, projectId), isNull(projects.deletedAt)));

  const project = await getProjectById(dependencies.db, projectId);
  if (!project) {
    return err({
      type: 'project-not-found',
      projectId,
      message: `Project ${projectId} not found after initializing its repository`,
    });
  }
  await dependencies.projects
    .invalidate(projectId, 'repository-changed')
    .catch((error: unknown) => {
      log.warn('initializeRepository: failed to invalidate the previous attachment', {
        projectId,
        error: String(error),
      });
    });

  appDbPokes.projects.poke({ projectId });
  return ok(project);
}
