import { and, eq, isNull } from 'drizzle-orm';
import { workspaceRegistryTable as workspaces } from '@core/features/workspaces/api/node/registry';
import type { HostWorkspaceGroupsData } from '@core/primitives/workspaces/api';
import { projects } from '@core/services/app-db/node/schema';
import {
  listProjectWorkspaces,
  type ListProjectWorkspacesDependencies,
} from './list-project-workspaces';

/** Machines-page scope key: this device or one SSH connection. */
export type WorkspaceGroupsHostKey = 'local' | `ssh:${string}`;

export function workspaceGroupsHostKey(input: {
  location: 'local' | 'remote';
  sshConnectionId: string | null;
}): WorkspaceGroupsHostKey {
  return input.location === 'remote' && input.sshConnectionId !== null
    ? `ssh:${input.sshConnectionId}`
    : 'local';
}

/**
 * The machines-page workspaces read: every project whose repository workspace lives on
 * the host, each with its mirror-served rows. Pure DB reads — grouping updates live
 * through the workspaces/tasks/projects pokes, never through host scans.
 */
export async function listHostWorkspaceGroups(
  dependencies: ListProjectWorkspacesDependencies,
  hostKey: WorkspaceGroupsHostKey
): Promise<HostWorkspaceGroupsData> {
  const hostFilter =
    hostKey === 'local'
      ? and(eq(workspaces.location, 'local'), isNull(workspaces.sshConnectionId))
      : and(
          eq(workspaces.location, 'remote'),
          eq(workspaces.sshConnectionId, hostKey.slice('ssh:'.length))
        );

  const projectRows = dependencies.db
    .select({ id: projects.id, name: projects.name })
    .from(projects)
    .innerJoin(workspaces, eq(workspaces.id, projects.repositoryWorkspaceId))
    .where(and(isNull(projects.deletedAt), hostFilter))
    .all();

  const groups = await Promise.all(
    projectRows.map(async (project) => {
      try {
        const listed = await listProjectWorkspaces(dependencies, project.id);
        return { project, workspaces: listed.rows, warnings: listed.warnings };
      } catch (error) {
        return {
          project,
          workspaces: [],
          warnings: [error instanceof Error ? error.message : String(error)],
        };
      }
    })
  );

  return {
    groups: groups.sort((left, right) => left.project.name.localeCompare(right.project.name)),
  };
}
