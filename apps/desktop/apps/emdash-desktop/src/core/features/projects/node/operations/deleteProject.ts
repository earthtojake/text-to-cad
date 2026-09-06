import { err, ok, type Result } from '@emdash/shared';
import type { Logger } from '@emdash/shared/logger';
import { and, eq, inArray, isNull } from 'drizzle-orm';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import { projectEvents } from '@core/features/projects/api/node/project-events';
import { projectSubject } from '@core/features/projects/contributions/subject';
import {
  killTaskSessions,
  type TaskSessionCleanup,
} from '@core/features/tasks/api/node/task-session-cleanup';
import { taskSubject } from '@core/features/tasks/contributions/subject';
import { operationHostRef } from '@core/features/workspaces/api/node/operation-host-ref';
import {
  removeProjectWorkspace,
  type WorkspaceRemovalBroker,
} from '@core/features/workspaces/api/node/operations/workspace-removal';
import {
  liveWorkspaces,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import type { MutationError } from '@core/primitives/wire/api/mutations';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { projects, tasks, type WorkspaceRow } from '@core/services/app-db/node/schema';
import type { MementosRuntimeClient } from '@core/services/runtime-broker/api/clients';

/**
 * Project deletion as plain desktop code (operation-log retirement spec §3, §7): the
 * project row tombstones first (so concurrent creation sees "project deleting"), the
 * desktop-local cascade — per-task session kill and row purge — completes immediately,
 * and the host-artifact halves ride the workspace removal surface: reachable
 * provenance worktrees remove through the fail-fast verb, unreachable ones get durable
 * deletion tombstones for the reconcile sweep (ADR 0006). Nothing submits to the
 * operations kernel.
 */

export type ProjectDeletionResult = Result<void, MutationError>;

export type ProjectDeletionDependencies = {
  db: AppDb;
  runtimes: WorkspaceRemovalBroker;
  getMementosRuntimeClient(): Promise<MementosRuntimeClient>;
  logger: Logger;
  projects: Pick<ProjectAttachmentManager, 'invalidate'>;
  pullRequests: { deleteProjectData(projectId: string): Promise<void> };
  sessionCleanup: TaskSessionCleanup;
  telemetry: Pick<TelemetryService, 'capture'>;
};

export async function deleteProject(
  dependencies: ProjectDeletionDependencies,
  projectId: string
): Promise<ProjectDeletionResult> {
  const { db } = dependencies;
  const createdAt = Date.now();
  const [project] = await db
    .select({
      id: projects.id,
      name: projects.name,
      repositoryWorkspaceId: projects.repositoryWorkspaceId,
      repositoryLocation: workspaces.location,
      repositorySshConnectionId: workspaces.sshConnectionId,
    })
    .from(projects)
    .leftJoin(workspaces, eq(workspaces.id, projects.repositoryWorkspaceId))
    .where(and(eq(projects.id, projectId), isNull(projects.deletedAt)))
    .limit(1);
  if (!project) {
    return err({ type: 'project-not-found', message: `Project ${projectId} was not found` });
  }

  // Tombstone first: admission checks (task/automation creation and deletion
  // preconditions) read `deletedAt`, so the cascade below runs against a project
  // already marked as deleting. Zero rows updated means a concurrent delete won.
  const tombstoned = db.transaction(
    (tx) =>
      tx
        .update(projects)
        .set({ deletedAt: new Date(createdAt).toISOString() })
        .where(and(eq(projects.id, projectId), isNull(projects.deletedAt)))
        .run().changes
  );
  if (tombstoned === 0) {
    return err({ type: 'project-deleting', message: 'Project is already being deleted.' });
  }
  appDbPokes.projects.poke({ projectId });
  await dependencies.projects.invalidate(projectId, 'deletion').catch((error: unknown) => {
    dependencies.logger.warn('deleteProject: failed to dispose project attachment', {
      projectId,
      error: String(error),
    });
  });

  const taskRows = await db.select().from(tasks).where(eq(tasks.projectId, projectId));
  const registryRows = await loadProjectRegistryRows(db, project);
  const registryRowById = new Map(registryRows.map((row) => [row.id, row]));
  const repository = {
    location: project.repositoryLocation,
    sshConnectionId: project.repositorySshConnectionId,
  };

  // Desktop-local cascade: kill each task's sessions best-effort, then purge its rows.
  // Conversation mirror rows keep their project link and die with the project row's
  // FK cascade — same as before; the host records survive and resync as adopted.
  for (const task of taskRows) {
    const workspace = task.workspaceId ? registryRowById.get(task.workspaceId) : undefined;
    const host = operationHostRef({ workspace, repository });
    await killTaskSessions(dependencies, task, host, workspace?.path ?? undefined);
    db.transaction((tx) => {
      tx.delete(tasks).where(eq(tasks.id, task.id)).run();
    });
    dependencies.telemetry.capture('task_deleted', { project_id: projectId, task_id: task.id });
  }
  appDbPokes.tasks.poke({ projectId });

  // Host-artifact cascade: reachable provenance worktrees remove through the verb,
  // unreachable ones tombstone for the sweep, everything else untracks.
  for (const row of registryRows) {
    await removeProjectWorkspace(db, dependencies.runtimes, {
      workspace: row,
      host: operationHostRef({ workspace: row, repository }),
      createdAt,
    });
  }
  appDbPokes.workspaces.poke({ projectId });

  await purgeProjectLocalState(dependencies, projectId);
  appDbPokes.projects.poke({ projectId });
  return ok(undefined);
}

/** Tracked registry rows referenced by the project: task workspaces + the repository row. */
async function loadProjectRegistryRows(
  db: AppDb,
  project: { id: string; repositoryWorkspaceId: string | null }
): Promise<WorkspaceRow[]> {
  const taskRows = await db
    .select({ workspaceId: tasks.workspaceId })
    .from(tasks)
    .where(eq(tasks.projectId, project.id));
  const candidateIds = new Set(
    taskRows.map((row) => row.workspaceId).filter((id): id is string => id !== null)
  );
  if (project.repositoryWorkspaceId) candidateIds.add(project.repositoryWorkspaceId);
  if (candidateIds.size === 0) return [];
  return db
    .select()
    .from(workspaces)
    .where(and(inArray(workspaces.id, [...candidateIds]), liveWorkspaces()));
}

async function purgeProjectLocalState(
  dependencies: ProjectDeletionDependencies,
  projectId: string
): Promise<void> {
  const { db } = dependencies;
  await dependencies.pullRequests.deleteProjectData(projectId);
  await db.delete(projects).where(eq(projects.id, projectId));
  const client = await dependencies.getMementosRuntimeClient();
  const taskRows = await db.select({ id: tasks.id }).from(tasks);
  const [projectResult, taskResult] = await Promise.all([
    client.deleteBySubject(projectSubject({ projectId })),
    client.deleteOrphans({ kind: taskSubject.kind, validKeys: taskRows.map(({ id }) => id) }),
  ]);
  if (!projectResult.success) throw new Error(projectResult.error.message);
  if (!taskResult.success) throw new Error(taskResult.error.message);
  projectEvents._emit('project:deleted', projectId);
  dependencies.telemetry.capture('project_deleted', { project_id: projectId });
}
