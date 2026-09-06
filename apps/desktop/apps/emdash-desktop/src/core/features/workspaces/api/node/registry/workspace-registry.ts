import type { WorkspaceRecord } from '@emdash/core/runtimes/workspace-registry/api';
import { err, ok, type Result } from '@emdash/shared';
import { and, eq, inArray, isNull, type SQL } from 'drizzle-orm';
import {
  tombstoneAttemptEpoch,
  type TombstoneTerminalStop,
} from '@core/primitives/reconcile/api/tombstone-attempts';
import type { AppDb, DrizzleTx } from '@core/services/app-db/node/db';
import {
  workspaces,
  type WorkspaceInsert,
  type WorkspaceRow,
} from '@core/services/app-db/node/schema';

export type WorkspaceHostIdentity = Readonly<{
  location: 'local' | 'remote';
  sshConnectionId: string | null;
}>;

export type WorkspaceObservation = Readonly<{
  path?: string | null;
  observedStatus?: WorkspaceRow['observedStatus'];
  // Host registry observations (ADR 0005): pushed by the records sync, refreshed
  // wholesale. Structural facts (kind, parentId, origin, host identity) are host-owned
  // there too, so they refresh rather than annotate.
  kind?: WorkspaceRow['kind'];
  parentId?: string | null;
  origin?: WorkspaceRow['origin'];
  location?: WorkspaceRow['location'];
  sshConnectionId?: string | null;
  observedGit?: WorkspaceRow['observedGit'];
  lastCreateOutcome?: WorkspaceRow['lastCreateOutcome'];
  lastRemovalAttempt?: WorkspaceRow['lastRemovalAttempt'];
  scriptOutcomes?: WorkspaceRow['scriptOutcomes'];
  runtimeOverlay?: WorkspaceRow['runtimeOverlay'];
  lastActivatedAt?: number | null;
  observedAt?: number | null;
}>;

export type WorkspaceClaimInput = Readonly<{
  host: WorkspaceHostIdentity;
  record: WorkspaceRecord;
  config?: WorkspaceInsert['config'];
  observedAt?: number;
}>;

export type WorkspaceClaimError =
  | {
      type: 'workspace-identity-conflict';
      path: string;
      incomingId: string;
      conflictingId: string;
    }
  | { type: 'workspace-tombstoned'; workspaceId: string };

export type WorkspaceRetrackError =
  | WorkspaceClaimError
  | { type: 'workspace-not-tracked'; workspaceId: string };

export type WorkspaceRegistryOptions = {
  now?: () => string;
};

export class WorkspaceRegistry {
  private readonly now: () => string;

  constructor(
    private readonly db: AppDb,
    options: WorkspaceRegistryOptions = {}
  ) {
    this.now = options.now ?? (() => new Date().toISOString());
  }

  getLive(id: string, tx?: DrizzleTx): WorkspaceRow | undefined {
    const [row] = this.source(tx)
      .select()
      .from(workspaces)
      .where(and(eq(workspaces.id, id), liveWorkspaces()))
      .limit(1)
      .all();
    return row;
  }

  findLiveByPath(
    location: NonNullable<WorkspaceRow['location']>,
    sshConnectionId: string | null,
    path: string,
    tx?: DrizzleTx
  ): WorkspaceRow | undefined {
    const hostIdentity =
      sshConnectionId === null
        ? isNull(workspaces.sshConnectionId)
        : eq(workspaces.sshConnectionId, sshConnectionId);
    return this.source(tx)
      .select()
      .from(workspaces)
      .where(
        and(
          eq(workspaces.location, location),
          hostIdentity,
          eq(workspaces.path, path),
          liveWorkspaces()
        )
      )
      .limit(1)
      .get();
  }

  /**
   * Claims one Host-acknowledged canonical record into the desktop Registry. Host
   * structural facts always win; the optional config is the caller-owned annotation.
   * An untracked canonical id is explicitly retracked, but a Tombstone is never
   * revived and a different live id at the same Host path is never repaired here.
   */
  claim(input: WorkspaceClaimInput, tx?: DrizzleTx): Result<WorkspaceRow, WorkspaceClaimError> {
    const source = this.source(tx);
    const existing = this.getAny(input.record.id, tx);
    if (existing?.deletionTombstone !== null && existing?.deletionTombstone !== undefined) {
      return err({ type: 'workspace-tombstoned', workspaceId: input.record.id });
    }
    if (existing && !sameWorkspaceHost(existing, input.host)) {
      return err({
        type: 'workspace-identity-conflict',
        path: input.record.path,
        incomingId: input.record.id,
        conflictingId: existing.id,
      });
    }

    const pathOwner = this.findLiveByPath(
      input.host.location,
      input.host.sshConnectionId,
      input.record.path,
      tx
    );
    if (pathOwner && pathOwner.id !== input.record.id) {
      return err({
        type: 'workspace-identity-conflict',
        path: input.record.path,
        incomingId: input.record.id,
        conflictingId: pathOwner.id,
      });
    }

    const observation = workspaceObservationFromRecord(
      input.record,
      input.host,
      input.observedAt ?? Date.now()
    );
    if (!existing) {
      return ok(
        this.insert(
          {
            id: input.record.id,
            type: input.host.location === 'remote' ? 'project-ssh' : 'local',
            ...observation,
            config: input.config ?? null,
            createdAt: new Date(input.record.createdAt).toISOString(),
          },
          tx
        )
      );
    }

    source
      .update(workspaces)
      .set({
        ...observation,
        ...(input.config !== undefined ? { config: input.config } : {}),
        untrackedAt: null,
        updatedAt: this.now(),
      })
      .where(eq(workspaces.id, input.record.id))
      .run();
    return ok(this.getAny(input.record.id, tx)!);
  }

  /**
   * Moves an existing mirror row to a different Host only after that Host returned the
   * same canonical UUID. This is the explicit Project-relink seam; Claim never changes
   * Host ownership and snapshots never call this method.
   */
  retrack(
    input: WorkspaceClaimInput,
    previousHost: WorkspaceHostIdentity,
    tx?: DrizzleTx
  ): Result<WorkspaceRow, WorkspaceRetrackError> {
    const existing = this.getLive(input.record.id, tx);
    if (!existing) {
      return err({ type: 'workspace-not-tracked', workspaceId: input.record.id });
    }
    if (existing.deletionTombstone !== null) {
      return err({ type: 'workspace-tombstoned', workspaceId: input.record.id });
    }
    if (!sameWorkspaceHost(existing, previousHost)) {
      return err({
        type: 'workspace-identity-conflict',
        path: input.record.path,
        incomingId: input.record.id,
        conflictingId: existing.id,
      });
    }

    const pathOwner = this.findLiveByPath(
      input.host.location,
      input.host.sshConnectionId,
      input.record.path,
      tx
    );
    if (pathOwner && pathOwner.id !== input.record.id) {
      return err({
        type: 'workspace-identity-conflict',
        path: input.record.path,
        incomingId: input.record.id,
        conflictingId: pathOwner.id,
      });
    }

    this.source(tx)
      .update(workspaces)
      .set({
        ...workspaceObservationFromRecord(input.record, input.host, input.observedAt ?? Date.now()),
        ...(input.config !== undefined ? { config: input.config } : {}),
        untrackedAt: null,
        updatedAt: this.now(),
      })
      .where(eq(workspaces.id, input.record.id))
      .run();
    return ok(this.getAny(input.record.id, tx)!);
  }

  /** Records desktop intent before the corresponding Host worktree create settles. */
  recordCreationIntent(values: WorkspaceInsert, tx?: DrizzleTx): WorkspaceRow {
    return this.insert(values, tx);
  }

  adopt(values: WorkspaceInsert, tx?: DrizzleTx): WorkspaceRow {
    return this.insert({ ...values, config: null }, tx);
  }

  refresh(id: string, observation: WorkspaceObservation, tx?: DrizzleTx): number {
    const { path, ...observed } = observation;
    return this.source(tx)
      .update(workspaces)
      .set({
        ...observed,
        ...(path !== undefined ? { path } : {}),
        updatedAt: this.now(),
      })
      .where(and(eq(workspaces.id, id), liveWorkspaces()))
      .run().changes;
  }

  updateConfig(id: string, config: WorkspaceInsert['config'], tx?: DrizzleTx): number {
    return this.source(tx)
      .update(workspaces)
      .set({ config, updatedAt: this.now() })
      .where(eq(workspaces.id, id))
      .run().changes;
  }

  /**
   * Marks one live row with a durable deletion tombstone (ADR 0006). Atomic and
   * first-writer-wins: the guard on a null `deletionTombstone` makes zero rows updated
   * mean "already tombstoned" (or no longer live), so a UI double-fire never overwrites
   * the frozen options. The row stays live — the visible pending state.
   */
  tombstone(
    id: string,
    tombstone: NonNullable<WorkspaceRow['deletionTombstone']>,
    tx?: DrizzleTx
  ): number {
    return this.source(tx)
      .update(workspaces)
      .set({ deletionTombstone: tombstone, updatedAt: this.now() })
      .where(and(eq(workspaces.id, id), liveWorkspaces(), isNull(workspaces.deletionTombstone)))
      .run().changes;
  }

  /**
   * The durable half of the Retry affordance (ADR 0006): advances the tombstone's
   * attempt epoch on the row itself, so the recorded terminal stop from the previous
   * epoch goes inert — durably. A registry sync restoring the host-written mark or an
   * app restart can never resurrect the cleared stop. Zero rows updated means no live
   * tombstoned row — a no-op.
   */
  retryTombstone(id: string, tx?: DrizzleTx): number {
    const row = this.getLive(id, tx);
    const tombstone = row?.deletionTombstone;
    if (!row || !tombstone) return 0;
    return this.source(tx)
      .update(workspaces)
      .set({
        deletionTombstone: { ...tombstone, attemptEpoch: tombstoneAttemptEpoch(tombstone) + 1 },
        updatedAt: this.now(),
      })
      .where(and(eq(workspaces.id, id), liveWorkspaces()))
      .run().changes;
  }

  /**
   * Records the durable terminal stop for one sweep attempt, tagged with the epoch
   * the attempt ran in. Epoch-guarded: a Retry that already advanced the epoch
   * invalidates the stale stop, so it is discarded rather than written.
   */
  recordTombstoneTerminalStop(id: string, stop: TombstoneTerminalStop, tx?: DrizzleTx): number {
    const row = this.getLive(id, tx);
    const tombstone = row?.deletionTombstone;
    if (!row || !tombstone) return 0;
    if (stop.epoch !== tombstoneAttemptEpoch(tombstone)) return 0;
    return this.source(tx)
      .update(workspaces)
      .set({
        deletionTombstone: { ...tombstone, terminalStop: stop },
        updatedAt: this.now(),
      })
      .where(and(eq(workspaces.id, id), liveWorkspaces()))
      .run().changes;
  }

  untrack(
    ids: readonly string[],
    untrackedAt: string,
    observation?: Partial<Pick<WorkspaceObservation, 'observedStatus' | 'observedAt'>>,
    tx?: DrizzleTx
  ): number {
    if (ids.length === 0) return 0;
    return this.source(tx)
      .update(workspaces)
      .set({
        untrackedAt,
        ...observation,
        updatedAt: this.now(),
      })
      .where(and(inArray(workspaces.id, [...ids]), liveWorkspaces()))
      .run().changes;
  }

  purge(ids: readonly string[], tx?: DrizzleTx): number {
    if (ids.length === 0) return 0;
    const source = this.source(tx);
    const tracked = source
      .select({ id: workspaces.id })
      .from(workspaces)
      .where(and(inArray(workspaces.id, [...ids]), liveWorkspaces()))
      .all();
    if (tracked.length > 0) {
      throw new Error(
        `Registry rows must be untracked before purge: ${tracked.map(({ id }) => id).join(', ')}`
      );
    }
    return source
      .delete(workspaces)
      .where(inArray(workspaces.id, [...ids]))
      .run().changes;
  }

  private source(tx?: DrizzleTx): AppDb {
    // AppDb and its transaction expose the same query-builder surface used by
    // this module; Drizzle does not publish a shared structural type for it.
    return (tx ?? this.db) as unknown as AppDb;
  }

  private getAny(id: string, tx?: DrizzleTx): WorkspaceRow | undefined {
    return this.source(tx).select().from(workspaces).where(eq(workspaces.id, id)).limit(1).get();
  }

  private insert(values: WorkspaceInsert, tx?: DrizzleTx): WorkspaceRow {
    const now = this.now();
    return this.source(tx)
      .insert(workspaces)
      .values({
        ...values,
        createdAt: values.createdAt ?? now,
        updatedAt: values.updatedAt ?? now,
        untrackedAt: null,
      })
      .returning()
      .get();
  }
}

export function workspaceObservationFromRecord(
  record: WorkspaceRecord,
  host: WorkspaceHostIdentity,
  observedAt: number
): WorkspaceObservation {
  return {
    kind: record.kind,
    path: record.path,
    parentId: record.parentId,
    origin: record.origin,
    observedStatus: record.observedStatus,
    observedGit: record.git === null ? null : { version: '2', ...record.git },
    lastCreateOutcome:
      record.lastCreateOutcome === null ? null : { version: '1', ...record.lastCreateOutcome },
    lastRemovalAttempt:
      record.lastRemovalAttempt === null ? null : { version: '1', ...record.lastRemovalAttempt },
    scriptOutcomes: null,
    runtimeOverlay: record.runtime === null ? null : { version: '1', ...record.runtime },
    lastActivatedAt: record.lastActivatedAt,
    observedAt,
    location: host.location,
    sshConnectionId: host.sshConnectionId,
  };
}

function sameWorkspaceHost(
  row: Pick<WorkspaceRow, 'location' | 'sshConnectionId'>,
  host: WorkspaceHostIdentity
): boolean {
  return row.location === host.location && row.sshConnectionId === host.sshConnectionId;
}

export function createWorkspaceRegistry(
  db: AppDb,
  options?: WorkspaceRegistryOptions
): WorkspaceRegistry {
  return new WorkspaceRegistry(db, options);
}

export function liveWorkspaces(): SQL {
  return isNull(workspaces.untrackedAt);
}

export function isAnnotatedWorkspace(row: {
  config: unknown | null;
  hasTaskLink?: boolean;
  isProjectRepository?: boolean;
}): boolean {
  return row.config !== null || row.hasTaskLink === true || row.isProjectRepository === true;
}

/** Read-side table export. All mutations must go through `WorkspaceRegistry`. */
export const workspaceRegistryTable = workspaces;
