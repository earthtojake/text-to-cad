import { hostRef } from '@emdash/core/primitives/host/api';
import type { WorkspaceRecord } from '@emdash/core/runtimes/workspace-registry/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { and, eq, inArray, isNull, or } from 'drizzle-orm';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import {
  createWorkspaceRegistry,
  liveWorkspaces,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { projects, tasks } from '@core/services/app-db/node/schema';

/**
 * Re-points an SSH project at a different connection. Host identity lives on
 * the workspace rows, so the repository row and every live remote workspace
 * of the project move together.
 */
export async function updateProjectConnection(
  db: AppDb,
  runtimes: Pick<RuntimeBroker, 'client'>,
  attachments: Pick<ProjectAttachmentManager, 'invalidate'>,
  projectId: string,
  connectionId: string
): Promise<void> {
  const [row] = await db
    .select({ repositoryWorkspaceId: projects.repositoryWorkspaceId })
    .from(projects)
    .where(and(eq(projects.id, projectId), isNull(projects.deletedAt)));
  if (!row) throw new Error(`Project ${projectId} not found`);
  if (!row.repositoryWorkspaceId) {
    throw new Error(`Project ${projectId} has no repository workspace`);
  }

  const registry = createWorkspaceRegistry(db);
  const repository = registry.getLive(row.repositoryWorkspaceId);
  if (repository?.location !== 'remote') {
    throw new Error(`Project ${projectId} is not an SSH project`);
  }

  const taskWorkspaceRows = await db
    .select({ workspaceId: tasks.workspaceId })
    .from(tasks)
    .where(and(eq(tasks.projectId, projectId), isNull(tasks.deletedAt)));
  const candidateIds = new Set<string>([repository.id]);
  for (const taskRow of taskWorkspaceRows) {
    if (taskRow.workspaceId) candidateIds.add(taskRow.workspaceId);
  }
  const remoteRows = await db
    .select()
    .from(workspaces)
    .where(
      and(
        or(inArray(workspaces.id, [...candidateIds]), eq(workspaces.parentId, repository.id)),
        eq(workspaces.location, 'remote'),
        liveWorkspaces()
      )
    );
  const foreignRow = remoteRows.find(
    (remoteRow) => remoteRow.sshConnectionId !== repository.sshConnectionId
  );
  if (foreignRow) {
    throw new Error(`Workspace ${foreignRow.id} does not belong to the Project's current Host`);
  }

  const destinationHost = hostRef('remote', connectionId);
  const destination = await runtimes.client(destinationHost);
  if (!destination.success) throw new Error(destination.error.message);

  const canonical = new Map<string, WorkspaceRecord>();
  for (const remoteRow of sortParentFirst(remoteRows)) {
    if (remoteRow.path === null) {
      throw new Error(`Workspace ${remoteRow.id} has no path`);
    }
    const resolved = await destination.data.workspaceRegistry.createWorkspace({
      workspaceId: remoteRow.id,
      path: remoteRow.path,
    });
    if (!resolved.success) {
      throw new Error(
        `Could not register Workspace ${remoteRow.id} on the destination Host (${resolved.error.type})`
      );
    }
    if (resolved.data.id !== remoteRow.id) {
      throw new Error(
        `Destination Host path '${resolved.data.path}' belongs to Workspace '${resolved.data.id}', not '${remoteRow.id}'`
      );
    }
    canonical.set(remoteRow.id, resolved.data);
  }

  const previousHost = {
    location: 'remote' as const,
    sshConnectionId: repository.sshConnectionId,
  };
  const nextHost = { location: 'remote' as const, sshConnectionId: connectionId };
  db.transaction((tx) => {
    for (const remoteRow of remoteRows) {
      const record = canonical.get(remoteRow.id);
      if (!record) throw new Error(`Host did not return Workspace ${remoteRow.id}`);
      const retracked = registry.retrack({ host: nextHost, record }, previousHost, tx);
      if (!retracked.success) {
        throw new Error(`Could not retrack Workspace ${remoteRow.id} (${retracked.error.type})`);
      }
    }
    tx.update(projects)
      .set({ updatedAt: new Date().toISOString() })
      .where(and(eq(projects.id, projectId), isNull(projects.deletedAt)))
      .run();
  });
  appDbPokes.projects.poke({ projectId });
  appDbPokes.workspaces.poke({ projectId });
  await attachments.invalidate(projectId, 'relink');
}

function sortParentFirst<T extends { id: string; parentId: string | null }>(rows: T[]): T[] {
  const byId = new Map(rows.map((row) => [row.id, row]));
  const depth = (row: T): number => {
    const seen = new Set([row.id]);
    let parentId = row.parentId;
    let result = 0;
    while (parentId !== null && byId.has(parentId) && !seen.has(parentId)) {
      seen.add(parentId);
      result += 1;
      parentId = byId.get(parentId)?.parentId ?? null;
    }
    return result;
  };
  return [...rows].sort(
    (left, right) => depth(left) - depth(right) || left.id.localeCompare(right.id)
  );
}
