import { hostRefFromParts, type HostRef } from '@emdash/core/primitives/host/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { and, eq, inArray, isNotNull, isNull, or } from 'drizzle-orm';
import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import {
  isAnnotatedWorkspace,
  liveWorkspaces,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import { getProvisionedWorkspaceBranch } from '@core/features/workspaces/api/node/workspace-branch';
import { activeTombstoneTerminalStop } from '@core/primitives/reconcile/api/tombstone-attempts';
import type { TaskLifecycleStatus } from '@core/primitives/tasks/api';
import type {
  ProjectWorkspaceGitStats,
  ProjectWorkspaceRow,
  ProjectWorkspaceTask,
  ProjectWorkspacesResult,
} from '@core/primitives/workspaces/api';
import type {
  WorkspaceConfig,
  WorkspaceCreateOutcome,
  WorkspaceDeletionTombstone,
  WorkspaceObservedGit,
  WorkspaceRuntimeOverlay,
} from '@core/primitives/workspaces/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { projects, tasks } from '@core/services/app-db/node/schema';

export type ProjectWorkspaceProjectRow = {
  id: string;
  path: string;
  repositoryWorkspaceId: string | null;
  repositoryWorkspaceLocation: 'local' | 'remote' | null;
  repositoryWorkspaceSshConnectionId: string | null;
};

export type ListProjectWorkspacesDependencies = {
  db: AppDb;
  /** Unused by the mirror read itself; shared with sibling operations (deletes). */
  runtimes: Pick<RuntimeBroker, 'client'>;
  taskSessions: Pick<TaskSessionManager, 'getTask'>;
};

type WorkspaceRow = {
  id: string;
  type: 'local' | 'project-ssh';
  kind: 'worktree' | 'repository' | 'directory' | null;
  location: 'local' | 'remote' | null;
  sshConnectionId: string | null;
  path: string | null;
  config: WorkspaceConfig | null;
  observedStatus: 'present' | 'missing' | null;
  observedGit: WorkspaceObservedGit | null;
  observedAt: number | null;
  deletionTombstone: WorkspaceDeletionTombstone | null;
  lastCreateOutcome: WorkspaceCreateOutcome | null;
  runtimeOverlay: WorkspaceRuntimeOverlay | null;
};

type TaskRow = {
  taskId: string;
  name: string;
  status: string;
  archivedAt: string | null;
  updatedAt: string;
  lastInteractedAt: string | null;
  workspaceId: string | null;
};

type RowCandidate = {
  kind: ProjectWorkspaceRow['kind'];
  path: string;
  branch?: string;
  isMain: boolean;
  prunable: boolean;
  workspace: WorkspaceRow | undefined;
  tasks: ProjectWorkspaceTask[];
};

/**
 * A pure mirror read (planning ticket 09): the host registry sync keeps the mirror's
 * observation columns fresh, so listing never scans the host. Callers wanting an
 * eager re-observation use the registry `refresh` verb; staleness is displayed from
 * `lastObservedAt`, not hidden behind a scan.
 */
export async function listProjectWorkspaces(
  dependencies: ListProjectWorkspacesDependencies,
  projectId: string
): Promise<ProjectWorkspacesResult> {
  const project = await getProjectWorkspaceProject(dependencies.db, projectId);
  const projectHost = projectWorkspaceHost(project);
  const taskRows = await getTaskRows(dependencies.db, projectId);
  const workspaceRows = await getWorkspaceRows(
    dependencies.db,
    project.repositoryWorkspaceId,
    taskRows.flatMap((row) => (row.workspaceId ? [row.workspaceId] : []))
  );

  const workspacesById = new Map(workspaceRows.map((workspace) => [workspace.id, workspace]));
  const tasksByWorkspaceId = groupTasks(taskRows);
  const candidates: RowCandidate[] = [];

  for (const workspace of workspaceRows) {
    if (!workspace.path) continue;
    const rowTasks = tasksByWorkspaceId.get(workspace.id) ?? [];
    const isMain = workspace.id === project.repositoryWorkspaceId;
    candidates.push({
      kind: isMain
        ? 'root'
        : isAnnotatedWorkspace({ config: workspace.config, hasTaskLink: rowTasks.length > 0 })
          ? 'workspace'
          : 'candidate',
      path: workspace.path,
      branch: workspace.observedGit?.branch ?? workspaceBranch(workspace),
      isMain,
      prunable: workspace.observedGit?.prunable ?? false,
      workspace,
      tasks: rowTasks,
    });
  }

  if (!candidates.some((candidate) => candidate.isMain)) {
    const rootWorkspace = project.repositoryWorkspaceId
      ? workspacesById.get(project.repositoryWorkspaceId)
      : undefined;
    candidates.push({
      kind: 'root',
      path: project.path,
      branch: rootWorkspace?.observedGit?.branch ?? workspaceBranch(rootWorkspace),
      isMain: true,
      prunable: false,
      workspace: rootWorkspace,
      tasks: rootWorkspace ? (tasksByWorkspaceId.get(rootWorkspace.id) ?? []) : [],
    });
  }

  const rows = candidates.map((candidate) =>
    buildCandidateRow({ taskSessions: dependencies.taskSessions }, project, projectHost, candidate)
  );

  rows.sort((left, right) => {
    if (left.kind === 'root') return -1;
    if (right.kind === 'root') return 1;
    return left.path.localeCompare(right.path);
  });

  const latestObservation = workspaceRows.reduce<number>(
    (latest, row) => Math.max(latest, row.observedAt ?? 0),
    0
  );

  return {
    scannedAt: new Date(latestObservation > 0 ? latestObservation : Date.now()).toISOString(),
    projectId,
    rows,
    totalBytes: rows.reduce((sum, row) => sum + (row.usage?.totalBytes ?? 0), 0),
    artifactBytes: rows.reduce((sum, row) => sum + (row.usage?.artifactBytes ?? 0), 0),
    warnings: [],
  };
}

export async function mapWithConcurrency<T, U>(
  items: readonly T[],
  limit: number,
  mapItem: (item: T) => Promise<U>
): Promise<U[]> {
  const results = new Array<U>(items.length);
  let nextIndex = 0;

  async function worker() {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      results[index] = await mapItem(items[index]!);
    }
  }

  const workers = Array.from({ length: Math.min(limit, items.length) }, () => worker());
  await Promise.all(workers);
  return results;
}

function buildCandidateRow(
  dependencies: Pick<ListProjectWorkspacesDependencies, 'taskSessions'>,
  project: ProjectWorkspaceProjectRow,
  projectHost: HostRef,
  candidate: RowCandidate
): ProjectWorkspaceRow {
  const remote = candidate.workspace?.location === 'remote' || projectHost.type === 'remote';
  const hasActiveSessions = candidate.tasks.some(
    (task) => !!dependencies.taskSessions.getTask(task.taskId)
  );
  const lastActivityAt = latest(
    candidate.tasks.flatMap((task) => [task.lastInteractedAt, task.updatedAt])
  );

  const observedAt = candidate.workspace?.observedAt;
  // A tombstoned row is already a pending deletion (ADR 0006): no second delete.
  const tombstone = candidate.workspace?.deletionTombstone ?? null;
  const pendingRemoval = tombstone !== null;
  const base: ProjectWorkspaceRow = {
    kind: candidate.kind,
    projectId: project.id,
    workspaceId: candidate.workspace?.id ?? null,
    path: candidate.path,
    branch: candidate.branch,
    tasks: candidate.tasks,
    usage: null,
    gitStats: mirrorGitStats(candidate.workspace?.observedGit ?? null),
    pathState: 'no-path',
    canCleanArtifacts: false,
    canDelete: candidate.kind !== 'root' && !remote && !pendingRemoval,
    hasActiveSessions,
    lastActivityAt,
    observedStatus: candidate.workspace?.observedStatus ?? undefined,
    lastObservedAt: observedAt ? new Date(observedAt).toISOString() : undefined,
    pendingRemoval,
    // Durable, epoch-guarded (ADR 0006): a Retry advanced past the stop's epoch hides
    // it here, so sync and restarts can never resurrect a cleared needs-attention.
    removalStop:
      tombstone !== null ? (activeTombstoneTerminalStop(tombstone) ?? undefined) : undefined,
    lastCreateOutcome: candidate.workspace?.lastCreateOutcome ?? undefined,
    runtimeOverlay: candidate.workspace?.runtimeOverlay ?? undefined,
    errors: [],
  };

  const observedMissing = candidate.workspace?.observedStatus === 'missing';
  if (candidate.prunable || observedMissing) {
    return {
      ...base,
      pathState: 'missing',
      pathIssue: {
        kind: candidate.prunable ? 'prunable' : 'path-gone',
        ...(candidate.prunable ? { reason: 'Git reports this worktree as prunable.' } : {}),
      },
    };
  }

  return {
    ...base,
    pathState: 'measured',
    canCleanArtifacts: !remote && !pendingRemoval,
  };
}

function mirrorGitStats(observedGit: WorkspaceObservedGit | null): ProjectWorkspaceGitStats | null {
  if (!observedGit) return null;
  if (observedGit.diffStats === null && observedGit.ahead === null && observedGit.behind === null) {
    return null;
  }
  return {
    added: observedGit.diffStats?.added ?? 0,
    removed: observedGit.diffStats?.deleted ?? 0,
    ahead: observedGit.ahead ?? 0,
    behind: observedGit.behind ?? 0,
  };
}

export async function getProjectWorkspaceProject(
  db: AppDb,
  projectId: string
): Promise<ProjectWorkspaceProjectRow> {
  const [project] = await db
    .select({
      id: projects.id,
      repositoryWorkspaceId: projects.repositoryWorkspaceId,
      repositoryWorkspacePath: workspaces.path,
      repositoryWorkspaceLocation: workspaces.location,
      repositoryWorkspaceSshConnectionId: workspaces.sshConnectionId,
    })
    .from(projects)
    .leftJoin(workspaces, eq(workspaces.id, projects.repositoryWorkspaceId))
    .where(and(eq(projects.id, projectId), isNull(projects.deletedAt)))
    .limit(1);
  if (!project) throw new Error('Project was not found.');
  if (!project.repositoryWorkspacePath) {
    throw new Error('Project has no repository workspace path.');
  }
  return {
    id: project.id,
    path: project.repositoryWorkspacePath,
    repositoryWorkspaceId: project.repositoryWorkspaceId,
    repositoryWorkspaceLocation: project.repositoryWorkspaceLocation,
    repositoryWorkspaceSshConnectionId: project.repositoryWorkspaceSshConnectionId,
  };
}

async function getWorkspaceRows(
  db: AppDb,
  repositoryWorkspaceId: string | null,
  taskWorkspaceIds: readonly string[]
): Promise<WorkspaceRow[]> {
  const scope = repositoryWorkspaceId
    ? or(
        eq(workspaces.id, repositoryWorkspaceId),
        eq(workspaces.parentId, repositoryWorkspaceId),
        taskWorkspaceIds.length > 0 ? inArray(workspaces.id, [...taskWorkspaceIds]) : undefined
      )
    : taskWorkspaceIds.length > 0
      ? inArray(workspaces.id, [...taskWorkspaceIds])
      : undefined;
  if (!scope) return [];
  return (await db
    .select({
      id: workspaces.id,
      type: workspaces.type,
      kind: workspaces.kind,
      location: workspaces.location,
      sshConnectionId: workspaces.sshConnectionId,
      path: workspaces.path,
      config: workspaces.config,
      observedStatus: workspaces.observedStatus,
      observedGit: workspaces.observedGit,
      observedAt: workspaces.observedAt,
      deletionTombstone: workspaces.deletionTombstone,
      lastCreateOutcome: workspaces.lastCreateOutcome,
      runtimeOverlay: workspaces.runtimeOverlay,
    })
    .from(workspaces)
    .where(and(scope, isNotNull(workspaces.path), liveWorkspaces()))) as WorkspaceRow[];
}

async function getTaskRows(db: AppDb, projectId: string): Promise<TaskRow[]> {
  return await db
    .select({
      taskId: tasks.id,
      name: tasks.name,
      status: tasks.status,
      archivedAt: tasks.archivedAt,
      updatedAt: tasks.updatedAt,
      lastInteractedAt: tasks.lastInteractedAt,
      workspaceId: tasks.workspaceId,
    })
    .from(tasks)
    .where(and(eq(tasks.projectId, projectId), isNull(tasks.deletedAt)));
}

function groupTasks(rows: TaskRow[]): Map<string, ProjectWorkspaceTask[]> {
  const grouped = new Map<string, ProjectWorkspaceTask[]>();
  for (const row of rows) {
    if (!row.workspaceId) continue;
    const list = grouped.get(row.workspaceId) ?? [];
    list.push({
      taskId: row.taskId,
      name: row.name,
      status: row.status as TaskLifecycleStatus,
      archivedAt: row.archivedAt ?? undefined,
      updatedAt: row.updatedAt,
      lastInteractedAt: row.lastInteractedAt ?? undefined,
    });
    grouped.set(row.workspaceId, list);
  }
  return grouped;
}

function workspaceBranch(workspace: WorkspaceRow | undefined): string | undefined {
  if (!workspace) return undefined;
  return (
    getProvisionedWorkspaceBranch({ kind: workspace.kind, config: workspace.config }) ?? undefined
  );
}

function latest(values: Array<string | undefined>): string | undefined {
  return values
    .filter((value): value is string => !!value)
    .sort()
    .at(-1);
}

export function projectWorkspaceHost(project: ProjectWorkspaceProjectRow): HostRef {
  return hostRefFromParts(
    project.repositoryWorkspaceLocation,
    project.repositoryWorkspaceSshConnectionId
  );
}
