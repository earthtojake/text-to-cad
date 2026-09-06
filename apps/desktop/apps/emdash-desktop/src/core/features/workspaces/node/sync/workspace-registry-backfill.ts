import {
  hostRefKey,
  isLocalHostRef,
  type HostRef,
  type SerializedHostRef,
} from '@emdash/core/primitives/host/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { and, eq, isNull } from 'drizzle-orm';
import {
  createWorkspaceRegistry,
  liveWorkspaces,
  workspaceRegistryTable as workspaces,
  type WorkspaceHostIdentity,
} from '@core/features/workspaces/api/node/registry';
import type { AppDb } from '@core/services/app-db/node/db';
import { AppDbKeyValueStore } from '@core/services/app-db/node/key-value-store';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { type WorkspaceRow } from '@core/services/app-db/node/schema';
import type { WorkspaceRegistryRuntimeClient } from '@core/services/runtime-broker/api/clients';
import {
  translateWorkspaceIdentity,
  type WorkspaceIdentityTranslationError,
} from '../../api/node/translate-workspace-identity';
import { loadWorkspaceAnnotations, type WorkspaceAnnotationIndex } from './workspace-annotations';

const BACKFILL_VERSION = 2 as const;
const MAX_FIXED_POINT_PASSES = 5;

type BackfillCompletion = { version: typeof BACKFILL_VERSION; completedAt: number };
type BackfillFlags = Record<SerializedHostRef, number | BackfillCompletion>;

export type WorkspaceRegistryBackfillResult =
  | { status: 'complete' }
  | { status: 'retry-needed'; message: string }
  | { status: 'terminal-failure'; message: string };

export interface WorkspaceRegistryBackfillServiceOptions {
  db: AppDb;
  runtimes: RuntimeBroker;
  onError?: (context: string, error: unknown) => void;
}

type BackfillPlan = {
  preserve: WorkspaceRow[];
  retire: WorkspaceRow[];
  annotations: WorkspaceAnnotationIndex;
};

/**
 * The sole production cutover from shipped desktop-owned Workspace state to the Host
 * registry. This module may translate legacy ids by path; normal Claim and snapshot
 * Observe deliberately may not. On the ordinary first-client cutover the Host starts
 * empty and preserves every proposed legacy id. A different canonical id is possible
 * only when this Host has already learned the path during the same cutover (for example
 * from another desktop or scanner adoption). Completion gates snapshot attachment.
 */
export class WorkspaceRegistryBackfillService {
  private readonly flags: AppDbKeyValueStore<BackfillFlags>;

  constructor(private readonly options: WorkspaceRegistryBackfillServiceOptions) {
    this.flags = new AppDbKeyValueStore<BackfillFlags>(options.db, 'workspace-registry-backfill');
  }

  async backfillHost(host: HostRef): Promise<WorkspaceRegistryBackfillResult> {
    const flagKey = hostRefKey(host);
    const completion = await this.flags.get(flagKey);
    if (isCurrentCompletion(completion)) return { status: 'complete' };

    const client = await this.options.runtimes.client(host);
    if (!client.success) {
      return { status: 'retry-needed', message: client.error.message };
    }

    try {
      const hostIdentity = hostIdentityFor(host);
      for (let pass = 0; pass < MAX_FIXED_POINT_PASSES; pass += 1) {
        const before = this.loadPlan(host);
        const fingerprint = planFingerprint(before);
        const result = await this.applyPlan(hostIdentity, client.data.workspaceRegistry, before);
        if (result.status !== 'complete') {
          this.report(host, result);
          return result;
        }

        const after = this.loadPlan(host);
        if (planFingerprint(after) === fingerprint) {
          await this.flags.setOrThrow(flagKey, {
            version: BACKFILL_VERSION,
            completedAt: Date.now(),
          });
          appDbPokes.workspaces.poke({});
          return { status: 'complete' };
        }
      }
      const result: WorkspaceRegistryBackfillResult = {
        status: 'retry-needed',
        message: 'Workspace state changed continuously during the production cutover',
      };
      this.report(host, result);
      return result;
    } catch (error) {
      const result: WorkspaceRegistryBackfillResult = {
        status: 'retry-needed',
        message: error instanceof Error ? error.message : String(error),
      };
      this.report(host, result, error);
      return result;
    }
  }

  private async applyPlan(
    host: WorkspaceHostIdentity,
    runtime: Pick<WorkspaceRegistryRuntimeClient, 'createWorkspace'>,
    plan: BackfillPlan
  ): Promise<WorkspaceRegistryBackfillResult> {
    const registry = createWorkspaceRegistry(this.options.db);

    for (const row of plan.preserve) {
      if (row.path === null) {
        this.options.onError?.(
          `workspace registry backfill skipped pathless (${row.id})`,
          new Error(`Legacy Workspace '${row.id}' has no path`)
        );
        continue;
      }
      if (row.deletionTombstone !== null) {
        return terminal(`Legacy Workspace '${row.id}' has a pending deletion Tombstone`);
      }

      const created = await runtime.createWorkspace({ workspaceId: row.id, path: row.path });
      if (!created.success && created.error.type === 'path-not-found') {
        this.options.onError?.(
          `workspace registry backfill skipped missing (${row.id})`,
          new Error(`Legacy Workspace path is missing: '${row.path}'`)
        );
        continue;
      }
      if (!created.success) {
        return terminal(
          `Host rejected legacy Workspace '${row.id}': ${JSON.stringify(created.error)}`
        );
      }

      const claim = {
        host,
        record: created.data,
        ...(row.config !== null ? { config: row.config } : {}),
      };
      const claimed =
        created.data.id === row.id
          ? registry.claim(claim)
          : translateWorkspaceIdentity(this.options.db, row.id, claim, row.path);
      if (!claimed.success) return translationFailure(row.id, claimed.error);
    }

    const retiredAt = new Date().toISOString();
    registry.untrack(
      plan.retire.map((row) => row.id),
      retiredAt
    );
    return { status: 'complete' };
  }

  private loadPlan(host: HostRef): BackfillPlan {
    const local = isLocalHostRef(host);
    const rows = this.options.db
      .select()
      .from(workspaces)
      .where(
        and(
          liveWorkspaces(),
          eq(workspaces.location, local ? 'local' : 'remote'),
          local ? isNull(workspaces.sshConnectionId) : eq(workspaces.sshConnectionId, host.id)
        )
      )
      .all();
    const annotations = loadWorkspaceAnnotations(
      this.options.db,
      rows.map((row) => row.id)
    );
    const byId = new Map(rows.map((row) => [row.id, row]));
    const preserveIds = new Set<string>();

    for (const row of rows) {
      if (
        row.config !== null ||
        annotations.taskWorkspaceIds.has(row.id) ||
        annotations.projectRepositoryWorkspaceIds.has(row.id) ||
        row.kind === 'repository' ||
        row.kind === 'directory' ||
        row.origin === 'registered'
      ) {
        preserveIds.add(row.id);
      }
    }
    for (const id of [...preserveIds]) {
      let parentId = byId.get(id)?.parentId ?? null;
      while (parentId !== null) {
        if (preserveIds.has(parentId)) break;
        preserveIds.add(parentId);
        parentId = byId.get(parentId)?.parentId ?? null;
      }
    }

    const preserve = rows.filter((row) => preserveIds.has(row.id));
    preserve.sort((left, right) => compareBackfillRows(left, right, byId, preserveIds));
    return {
      preserve,
      retire: rows.filter((row) => !preserveIds.has(row.id)),
      annotations,
    };
  }

  private report(
    host: HostRef,
    result: Exclude<WorkspaceRegistryBackfillResult, { status: 'complete' }>,
    error: unknown = new Error(result.message)
  ): void {
    this.options.onError?.(
      `workspace registry backfill ${result.status} (${hostRefKey(host)})`,
      error
    );
  }
}

function compareBackfillRows(
  left: WorkspaceRow,
  right: WorkspaceRow,
  byId: ReadonlyMap<string, WorkspaceRow>,
  preserveIds: ReadonlySet<string>
): number {
  const leftDepth = backfillDepth(left, byId, preserveIds);
  const rightDepth = backfillDepth(right, byId, preserveIds);
  return (
    leftDepth - rightDepth ||
    Number(left.kind === 'worktree') - Number(right.kind === 'worktree') ||
    left.id.localeCompare(right.id)
  );
}

function backfillDepth(
  row: WorkspaceRow,
  byId: ReadonlyMap<string, WorkspaceRow>,
  preserveIds: ReadonlySet<string>
): number {
  const seen = new Set([row.id]);
  let depth = 0;
  let parentId = row.parentId;
  while (parentId !== null && preserveIds.has(parentId) && !seen.has(parentId)) {
    seen.add(parentId);
    depth += 1;
    parentId = byId.get(parentId)?.parentId ?? null;
  }
  return depth;
}

function planFingerprint(plan: BackfillPlan): string {
  return JSON.stringify({
    preserve: plan.preserve.map((row) => [
      row.id,
      row.path,
      row.parentId,
      row.kind,
      row.origin,
      row.config,
      plan.annotations.taskWorkspaceIds.has(row.id),
      plan.annotations.projectRepositoryWorkspaceIds.has(row.id),
    ]),
    retire: plan.retire.map((row) => row.id),
  });
}

function translationFailure(
  workspaceId: string,
  error: WorkspaceIdentityTranslationError
): WorkspaceRegistryBackfillResult {
  return terminal(
    `Desktop could not translate legacy Workspace '${workspaceId}': ${JSON.stringify(error)}`
  );
}

function terminal(message: string): WorkspaceRegistryBackfillResult {
  return { status: 'terminal-failure', message };
}

function isCurrentCompletion(value: number | BackfillCompletion | null): boolean {
  return typeof value === 'object' && value !== null && value.version === BACKFILL_VERSION;
}

function hostIdentityFor(host: HostRef): WorkspaceHostIdentity {
  return isLocalHostRef(host)
    ? { location: 'local', sshConnectionId: null }
    : { location: 'remote', sshConnectionId: host.id };
}
