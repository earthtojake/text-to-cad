import {
  formatHostRef,
  hostRefFromParts,
  type HostRef,
  type SerializedHostRef,
} from '@emdash/core/primitives/host/api';
import { err, ok, type Result } from '@emdash/shared';
import { and, eq, isNull } from 'drizzle-orm';
import { tombstoneConversationForRemoval } from '@core/features/conversations/api/node/operations/conversation-removal';
import {
  conversationRegistryTable as conversationRows,
  liveConversations,
} from '@core/features/conversations/api/node/registry';
import { PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE } from '@core/features/projects/api/attachments';
import { projectIsBeingDeleted } from '@core/features/projects/api/node/project-deletion';
import { operationHostRef } from '@core/features/workspaces/api/node/operation-host-ref';
import {
  createWorkspaceRegistry,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import { tombstoneWorkspaceRow } from '@core/features/workspaces/api/node/registry/workspace-tombstones';
import type { MutationAck, MutationError } from '@core/primitives/wire/api/mutations';
import type { AppDb, DrizzleTx } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { projects, tasks, type WorkspaceRow } from '@core/services/app-db/node/schema';
import { reconcileSweepTriggers } from '@core/services/reconcile-sweep/node/reconcile-sweep-triggers';

/**
 * Workspace removal through the host registry verbs (ADR 0005): one fail-fast
 * `deleteWorktree`/`deleteWorkspace` RPC against an effectively attached Project,
 * then the mirror row is untracked. If attachment disappears, the interactive
 * mutation refuses and leaves the mirror unchanged; it never creates recovery work.
 * Archive differs from delete only in the desktop annotation; host-side both remove
 * the worktree with `deleteBranch: false`.
 */

export type WorkspaceRemovalResult = Result<MutationAck, MutationError>;

type DeleteVerbError = { type: string; message?: string };

/**
 * Structural slice of the runtime broker: just the two delete verbs this module
 * calls. The production `RuntimeBroker` satisfies it; tests fake it directly.
 */
export type WorkspaceRemovalBroker = {
  client(host: HostRef): Promise<
    Result<
      {
        workspaceRegistry: {
          deleteWorktree(input: {
            workspaceId: string;
            deleteBranch: boolean;
          }): Promise<Result<void, DeleteVerbError>>;
          deleteWorkspace(input: { workspaceId: string }): Promise<Result<void, DeleteVerbError>>;
        };
      },
      { type: string; message: string }
    >
  >;
};

export type ArchiveWorkspaceInput = {
  projectId: string;
  workspaceId?: string;
  workspacePath: string;
  branchName?: string;
};

export async function deleteWorkspaceThroughRegistry(
  db: AppDb,
  runtimes: WorkspaceRemovalBroker,
  workspaceId: string,
  options: { deleteBranch?: boolean; deleteConversations?: boolean } = {}
): Promise<WorkspaceRemovalResult> {
  const workspace = createWorkspaceRegistry(db).getLive(workspaceId);
  if (!workspace) {
    return err({ type: 'workspace-not-found', message: `Workspace ${workspaceId} was not found` });
  }
  if (workspace.kind === 'repository') {
    return err({ type: 'root-refused', message: 'Repository root cannot be deleted.' });
  }
  const [task] = await db.select().from(tasks).where(eq(tasks.workspaceId, workspaceId)).limit(1);
  const [project] = task ? await getProjectRemovalRow(db, task.projectId) : [];
  return removeWorkspaceThroughRegistry(db, runtimes, {
    workspace,
    workspacePath: workspace.path ?? undefined,
    projectId: project?.id,
    host: operationHostRef({
      workspace,
      repository: project && {
        location: project.repositoryLocation,
        sshConnectionId: project.repositorySshConnectionId,
      },
    }),
    requireUnused: true,
    deleteBranch: options.deleteBranch ?? false,
    deleteConversations: options.deleteConversations ?? false,
  });
}

export async function deleteWorkspacePathThroughRegistry(
  db: AppDb,
  runtimes: WorkspaceRemovalBroker,
  input: ArchiveWorkspaceInput,
  options: { deleteConversations?: boolean } = {}
): Promise<WorkspaceRemovalResult> {
  return removeWorkspacePathThroughRegistry(db, runtimes, input, {
    requireUnused: true,
    deleteConversations: options.deleteConversations ?? false,
  });
}

export async function archiveWorkspaceThroughRegistry(
  db: AppDb,
  runtimes: WorkspaceRemovalBroker,
  input: ArchiveWorkspaceInput
): Promise<WorkspaceRemovalResult> {
  return removeWorkspacePathThroughRegistry(db, runtimes, input, { requireUnused: false });
}

async function removeWorkspacePathThroughRegistry(
  db: AppDb,
  runtimes: WorkspaceRemovalBroker,
  input: ArchiveWorkspaceInput,
  options: { requireUnused: boolean; deleteConversations?: boolean }
): Promise<WorkspaceRemovalResult> {
  const [project] = await getProjectRemovalRow(db, input.projectId, {
    liveOnly: true,
  });
  if (!project) {
    return err({ type: 'project-not-found', message: `Project ${input.projectId} was not found` });
  }
  const registry = createWorkspaceRegistry(db);
  // Rows discovered by scan may arrive without a registry id; the mirror row for the
  // same path (kept complete by registry sync) carries the host record's identity.
  const workspace = input.workspaceId
    ? registry.getLive(input.workspaceId)
    : findLiveWorkspaceByPath(db, input.workspacePath);
  if (input.workspaceId && !workspace) {
    return err({
      type: 'workspace-not-found',
      message: `Workspace ${input.workspaceId} was not found`,
    });
  }
  return removeWorkspaceThroughRegistry(db, runtimes, {
    workspace,
    workspacePath: input.workspacePath,
    projectId: project.id,
    host: operationHostRef({
      workspace,
      repository: {
        location: project.repositoryLocation,
        sshConnectionId: project.repositorySshConnectionId,
      },
    }),
    requireUnused: options.requireUnused && input.workspaceId !== undefined,
    deleteConversations: options.deleteConversations ?? false,
  });
}

async function removeWorkspaceThroughRegistry(
  db: AppDb,
  runtimes: WorkspaceRemovalBroker,
  params: {
    workspace: WorkspaceRow | undefined;
    workspacePath: string | undefined;
    projectId: string | undefined;
    host: HostRef;
    requireUnused: boolean;
    deleteBranch?: boolean;
    deleteConversations?: boolean;
  }
): Promise<WorkspaceRemovalResult> {
  const createdAt = Date.now();
  const workspaceId = params.workspace?.id;

  if (!workspaceId) {
    return err({ type: 'workspace-not-found', message: 'Workspace was not found.' });
  }
  const precondition = workspacePreconditionOutsideTx(db, {
    projectId: params.projectId,
    workspaceId,
    requireUnused: params.requireUnused,
  });
  if (precondition) return err(precondition);

  // The host record is removed first, fail-fast: only a confirmed host-side removal
  // untracks the mirror row, so a failed call leaves everything intact. Interactive
  // mutations never create recovery work when attachment disappears mid-call.
  if (params.workspace?.kind === 'worktree' || params.workspace?.kind === 'directory') {
    const client = await runtimes.client(params.host);
    if (!client.success) {
      return err({
        type: 'project-unavailable',
        message: PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE,
      });
    }
    const verb = client.data.workspaceRegistry;
    const removed =
      params.workspace.kind === 'worktree'
        ? await verb.deleteWorktree({ workspaceId, deleteBranch: params.deleteBranch ?? false })
        : await verb.deleteWorkspace({ workspaceId });
    if (!removed.success) {
      if (removed.error.type === 'host-unreachable') {
        return err({
          type: 'project-unavailable',
          message: PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE,
        });
      }
      return err({
        type: 'delete-failed',
        message: describeDeleteVerbError(removed.error),
      });
    }
  }

  const untracked = untrackWorkspaceInline(db, {
    workspaceId,
    requireUnused: params.requireUnused,
    createdAt,
  });
  if (!untracked.success) return untracked;
  // Opt-in only (spec §7.1): removal defaults to archive semantics — records survive with
  // dangling paths and stay resumable if the path is recreated. The delete verbs never
  // touch conversation records; the coupling is these explicit per-record tombstones,
  // converged by the conversations reconcile-sweep kind (ADR 0006).
  if (params.deleteConversations) {
    tombstoneWorkspaceConversationDeletions(db, {
      workspacePath: params.workspacePath,
      host: params.host,
      createdAt,
    });
    // The host is reachable (the delete verb just succeeded): sweep the freshly
    // written conversation tombstones now instead of waiting for the backstop.
    reconcileSweepTriggers.poke(params.host);
  }
  appDbPokes.workspaces.poke({ projectId: params.projectId });
  return ok({});
}

/**
 * The project-delete cascade's per-row workspace removal (spec §7.3): provenance
 * worktrees (rows emdash created, `config != NULL`) go through the same fail-fast
 * `deleteWorktree` verb as single deletes — reachable host removes now, unreachable
 * host gets a durable deletion tombstone for the reconcile sweep (ADR 0006). Adopted
 * rows and the repository row untrack only — emdash never removes artifacts it did
 * not create as part of a bulk delete. Deletion intent is never discarded (spec §9):
 * a failed verb on a reachable host also keeps the tombstone alive, so the sweep
 * retries it under the normal transient/terminal handling while the project row
 * itself still deletes.
 */
export async function removeProjectWorkspace(
  db: AppDb,
  runtimes: WorkspaceRemovalBroker,
  params: { workspace: WorkspaceRow; host: HostRef; createdAt: number }
): Promise<'removed' | 'tombstoned' | 'untracked'> {
  const { workspace, host, createdAt } = params;
  const registry = createWorkspaceRegistry(db, {
    now: () => new Date(createdAt).toISOString(),
  });
  const isProvenanceWorktree =
    workspace.kind === 'worktree' && workspace.path !== null && workspace.config !== null;
  if (!isProvenanceWorktree) {
    registry.untrack([workspace.id], new Date(createdAt).toISOString());
    return 'untracked';
  }
  const tombstone = () => {
    const written = tombstoneWorkspaceRow(db, {
      workspace,
      options: { deleteBranch: false, deleteConversations: false },
      createdAt,
    });
    if (written.success) reconcileSweepTriggers.poke(host);
    return 'tombstoned' as const;
  };
  const client = await runtimes.client(host);
  if (!client.success) return tombstone();
  const removed = await client.data.workspaceRegistry
    .deleteWorktree({ workspaceId: workspace.id, deleteBranch: false })
    .catch(() => ({ success: false as const, error: { type: 'remove-failed' as const } }));
  if (!removed.success) return tombstone();
  registry.untrack([workspace.id], new Date(createdAt).toISOString());
  return 'removed';
}

/**
 * The `deleteConversations` cascade (spec §7.1), tombstone-writing shape (ADR 0006):
 * marks the workspace's cached same-path, same-host conversation records with their
 * own durable deletion tombstones — one atomic transaction, duplicates suppressed —
 * and lets the conversations reconcile-sweep kind converge them on sweeps of the same
 * host. Both removal paths share it: the reachable-host delete flow after its verb
 * succeeds, and the workspaces sweep kind executing a frozen offline tombstone.
 * Same-host ordering (worktree before conversations or the reverse) is a heuristic
 * only — conversation removal tolerates the workspace already being gone.
 */
export function tombstoneWorkspaceConversationDeletions(
  db: AppDb,
  params: { workspacePath: string | undefined; host: HostRef; createdAt: number }
): number {
  const conversationIds = snapshotWorkspaceConversationIds(db, {
    workspacePath: params.workspacePath,
    hostRef: formatHostRef(params.host),
  });
  if (conversationIds.length === 0) return 0;
  let written = 0;
  db.transaction((tx) => {
    for (const conversationId of conversationIds) {
      const { outcome } = tombstoneConversationForRemoval(tx, {
        conversationId,
        createdAt: params.createdAt,
      });
      if (outcome === 'tombstoned') written += 1;
    }
  });
  if (written > 0) appDbPokes.conversations.poke({});
  return written;
}

function describeDeleteVerbError(error: DeleteVerbError): string {
  switch (error.type) {
    case 'not-a-worktree':
      return 'The record is not a worktree.';
    case 'remove-failed':
      return typeof error.message === 'string' ? error.message : 'Worktree removal failed.';
    default:
      return `Workspace deletion failed (${error.type}).`;
  }
}

function findLiveWorkspaceByPath(db: AppDb, workspacePath: string): WorkspaceRow | undefined {
  const [row] = db
    .select()
    .from(workspaces)
    .where(and(eq(workspaces.path, workspacePath), isNull(workspaces.untrackedAt)))
    .limit(1)
    .all();
  return row;
}

/**
 * Snapshot-compiles the cascade's targets: the workspace's cached conversation records
 * with the same observed path on the same host.
 */
function snapshotWorkspaceConversationIds(
  db: AppDb,
  params: { workspacePath: string | undefined; hostRef: SerializedHostRef }
): string[] {
  if (!params.workspacePath) return [];
  const rows = db
    .select()
    .from(conversationRows)
    .where(and(eq(conversationRows.workspacePath, params.workspacePath), liveConversations()))
    .all();
  return rows
    .filter((row) => {
      try {
        return (
          formatHostRef(hostRefFromParts(row.location, row.sshConnectionId)) === params.hostRef
        );
      } catch {
        return false;
      }
    })
    .map((row) => row.id);
}

function untrackWorkspaceInline(
  db: AppDb,
  input: {
    workspaceId: string;
    requireUnused: boolean;
    createdAt: number;
  }
): WorkspaceRemovalResult {
  const registry = createWorkspaceRegistry(db, {
    now: () => new Date(input.createdAt).toISOString(),
  });
  let failure: MutationError | undefined;
  db.transaction((tx) => {
    failure = workspacePrecondition(tx, {
      workspaceId: input.workspaceId,
      requireUnused: input.requireUnused,
    });
    if (failure) return;
    registry.untrack([input.workspaceId], new Date(input.createdAt).toISOString(), undefined, tx);
  });
  return failure ? err(failure) : ok({});
}

/** Project name + repository-workspace host identity, for removal routing. */
function getProjectRemovalRow(db: AppDb, projectId: string, options: { liveOnly?: boolean } = {}) {
  return db
    .select({
      id: projects.id,
      name: projects.name,
      repositoryPath: workspaces.path,
      repositoryLocation: workspaces.location,
      repositorySshConnectionId: workspaces.sshConnectionId,
    })
    .from(projects)
    .leftJoin(workspaces, eq(workspaces.id, projects.repositoryWorkspaceId))
    .where(
      options.liveOnly
        ? and(eq(projects.id, projectId), isNull(projects.deletedAt))
        : eq(projects.id, projectId)
    )
    .limit(1);
}

function workspacePreconditionOutsideTx(
  db: AppDb,
  input: { projectId?: string; workspaceId?: string; requireUnused: boolean }
): MutationError | undefined {
  let failure: MutationError | undefined;
  db.transaction((tx) => {
    failure = workspacePrecondition(tx, input);
  });
  return failure;
}

function workspacePrecondition(
  tx: DrizzleTx,
  input: { projectId?: string; workspaceId?: string; requireUnused: boolean }
): MutationError | undefined {
  if (input.projectId && projectIsBeingDeleted(tx, input.projectId)) {
    return { type: 'project-deleting', message: 'Project is being deleted.' };
  }
  if (
    input.requireUnused &&
    input.workspaceId &&
    workspaceHasLiveTaskInTransaction(tx, input.workspaceId)
  ) {
    return {
      type: 'workspace-in-use',
      message: 'Workspace is still referenced by an active task.',
    };
  }
  return undefined;
}

function workspaceHasLiveTaskInTransaction(tx: DrizzleTx, workspaceId: string): boolean {
  return (
    tx
      .select({ id: tasks.id })
      .from(tasks)
      .where(and(eq(tasks.workspaceId, workspaceId), isNull(tasks.deletedAt)))
      .limit(1)
      .get() !== undefined
  );
}
