import { randomUUID } from 'node:crypto';
import { isLocalHostRef, type HostRef } from '@emdash/core/primitives/host/api';
import type {
  CreateWorkspaceError,
  CreateWorktreeError,
  WorkspaceNotFoundError,
  WorkspaceRecord,
} from '@emdash/core/runtimes/workspace-registry/api';
import type { HostRuntimesClient, RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { err, type Result } from '@emdash/shared';
import { createController, type Controller } from '@emdash/wire/rpc';
import { and, eq, inArray, isNull } from 'drizzle-orm';
import {
  createWorkspaceRegistry,
  liveWorkspaces,
  workspaceRegistryTable as workspaces,
  type WorkspaceClaimError,
} from '@core/features/workspaces/api/node/registry';
import { workspaceHostStorage } from '@core/features/workspaces/api/node/workspace-identity-service';
import {
  workspaceRegistryWireContract,
  type ListWorkspacesInput,
} from '@core/features/workspaces/api/registry-wire-contract';
import {
  abandonWorkspaceRemoval,
  decodeWorkspaceHost,
  retryWorkspaceRemoval,
} from '@core/features/workspaces/node/operations/removal-affordances';
import type { WorkspaceConfig, WorkspaceMirrorRow } from '@core/primitives/workspaces/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { projects, tasks, type WorkspaceRow } from '@core/services/app-db/node/schema';
import type { ReconcileSweepHandle } from '@core/services/reconcile-sweep/node/reconcile-sweep-service';

export type CreateWorkspaceRegistryWireControllerOptions = {
  db: AppDb;
  runtimes: RuntimeBroker;
  /** The reconcile sweep, for the Retry / Untrack-anyway affordances (ADR 0006). */
  sweep: ReconcileSweepHandle;
  /** Test seam; production mints random UUIDs for the create verbs. */
  mintId?: () => string;
};

/**
 * The consolidated renderer workspace API (ADR 0005): reads serve from the mirror,
 * verbs pass through 1:1 to the host registry runtime resolved by host ref. A verb
 * against an unreachable host returns the broker's typed resolve error with no side
 * effects — nothing is queued, ever. Create success Claims the mirror row immediately
 * (with the client-owned config annotation) so links can attach before sync catches up.
 */
export function createWorkspaceRegistryWireController(
  options: CreateWorkspaceRegistryWireControllerOptions
): Controller {
  const mintId = options.mintId ?? randomUUID;
  const withRegistry = async <T, E>(
    host: HostRef,
    work: (registry: HostRuntimesClient['workspaceRegistry']) => Promise<Result<T, E>>
  ) => {
    const client = await options.runtimes.client(host);
    if (!client.success) return err(client.error);
    return work(client.data.workspaceRegistry);
  };

  return createController(workspaceRegistryWireContract, {
    listWorkspaces: (input) => listWorkspaces(options.db, input),

    createWorkspace: ({ host, path, config }) =>
      withRegistry<WorkspaceRecord, CreateWorkspaceError | WorkspaceClaimError>(
        host,
        async (registry) => {
          const result = await registry.createWorkspace({ workspaceId: mintId(), path });
          if (result.success) {
            const claimed = claimMirrorRow(options.db, host, result.data, config);
            if (!claimed.success) return claimed;
          }
          return result;
        }
      ),

    createWorktree: ({ host, config, ...spec }) =>
      withRegistry<WorkspaceRecord, CreateWorktreeError | WorkspaceClaimError>(
        host,
        async (registry) => {
          const result = await registry.createWorktree({
            workspaceId: mintId(),
            repositoryId: spec.repositoryId,
            branch: spec.branch,
            baseRef: spec.baseRef,
            path: spec.path,
            preservePatterns: spec.preservePatterns ?? [],
            ...(spec.publish !== undefined && { publish: spec.publish }),
          });
          if (result.success) {
            const claimed = claimMirrorRow(options.db, host, result.data, config);
            if (!claimed.success) return claimed;
          }
          return result;
        }
      ),

    activateWorkspace: ({ host, workspaceId }) =>
      withRegistry(host, (registry) => registry.activateWorkspace({ workspaceId })),

    deactivateWorkspace: ({ host, workspaceId }) =>
      withRegistry(host, (registry) => registry.deactivateWorkspace({ workspaceId })),

    deleteWorkspace: ({ host, workspaceId }) =>
      withRegistry(host, (registry) => registry.deleteWorkspace({ workspaceId })),

    deleteWorktree: ({ host, workspaceId, deleteBranch }) =>
      withRegistry(host, (registry) =>
        registry.deleteWorktree({ workspaceId, deleteBranch: deleteBranch ?? false })
      ),

    refresh: ({ host, workspaceId }) =>
      withRegistry(host, (registry) =>
        registry.refresh(workspaceId === undefined ? {} : { workspaceId })
      ),

    updateWorktree: ({ host, workspaceId, remote, sourceRef }) =>
      withRegistry(host, (registry) => registry.updateWorktree({ workspaceId, remote, sourceRef })),

    retryStep: ({ host, workspaceId, step }) =>
      withRegistry<WorkspaceRecord, WorkspaceNotFoundError | WorkspaceClaimError>(
        host,
        async (registry) => {
          const result = await registry.retryStep({ workspaceId, step });
          if (result.success) {
            const claimed = claimMirrorRow(options.db, host, result.data, undefined);
            if (!claimed.success) return claimed;
          }
          return result;
        }
      ),

    untrackWorkspace: async ({ workspaceId }) => {
      createWorkspaceRegistry(options.db).untrack([workspaceId], new Date().toISOString());
      appDbPokes.workspaces.poke({});
    },

    retryWorkspaceRemoval: async ({ workspaceId }) =>
      retryWorkspaceRemoval(options.db, options.sweep, workspaceId),

    abandonWorkspaceRemoval: async ({ workspaceId }) =>
      abandonWorkspaceRemoval(options.db, options.sweep, workspaceId),
  });
}

async function listWorkspaces(
  db: AppDb,
  input: ListWorkspacesInput
): Promise<WorkspaceMirrorRow[]> {
  const tracking = input.includeUntracked ? undefined : liveWorkspaces();
  const rows =
    'host' in input.scope
      ? db
          .select()
          .from(workspaces)
          .where(and(tracking, hostScopeFilter(input.scope.host)))
          .all()
      : listProjectRows(db, input.scope.projectId, tracking);
  return rows.map(toMirrorRow);
}

function hostScopeFilter(host: HostRef) {
  return isLocalHostRef(host)
    ? and(eq(workspaces.location, 'local'), isNull(workspaces.sshConnectionId))
    : and(eq(workspaces.location, 'remote'), eq(workspaces.sshConnectionId, host.id));
}

function listProjectRows(
  db: AppDb,
  projectId: string,
  tracking: ReturnType<typeof liveWorkspaces> | undefined
): WorkspaceRow[] {
  const taskLinked = db
    .select({ workspaceId: tasks.workspaceId })
    .from(tasks)
    .where(eq(tasks.projectId, projectId))
    .all()
    .flatMap((row) => (row.workspaceId ? [row.workspaceId] : []));
  const [project] = db
    .select({ repositoryWorkspaceId: projects.repositoryWorkspaceId })
    .from(projects)
    .where(eq(projects.id, projectId))
    .all();
  const ids = [
    ...new Set([
      ...taskLinked,
      ...(project?.repositoryWorkspaceId ? [project.repositoryWorkspaceId] : []),
    ]),
  ];
  if (ids.length === 0) return [];
  return db
    .select()
    .from(workspaces)
    .where(and(tracking, inArray(workspaces.id, ids)))
    .all();
}

function toMirrorRow(row: WorkspaceRow): WorkspaceMirrorRow {
  return {
    id: row.id,
    host: decodeWorkspaceHost(row),
    kind: row.kind,
    path: row.path,
    parentId: row.parentId,
    origin: row.origin,
    config: row.config,
    observedStatus: row.observedStatus,
    observedGit: row.observedGit,
    lastCreateOutcome: row.lastCreateOutcome,
    lastRemovalAttempt: row.lastRemovalAttempt,
    scriptOutcomes: row.scriptOutcomes,
    runtimeOverlay: row.runtimeOverlay,
    lastActivatedAt: row.lastActivatedAt,
    observedAt: row.observedAt,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
    untrackedAt: row.untrackedAt,
  };
}

/**
 * Create success Claims the canonical mirror row immediately, including explicit
 * retracking and Tombstone refusal. Snapshot Observe later refreshes the same Host facts.
 */
function claimMirrorRow(
  db: AppDb,
  host: HostRef,
  record: WorkspaceRecord,
  config: WorkspaceConfig | undefined
) {
  const registry = createWorkspaceRegistry(db);
  const { location, sshConnectionId } = workspaceHostStorage(host);
  const claimed = registry.claim({
    host: { location, sshConnectionId },
    record,
    ...(config !== undefined ? { config } : {}),
  });
  if (claimed.success) appDbPokes.workspaces.poke({});
  return claimed.success ? { success: true as const, data: undefined } : claimed;
}
