import { err, ok, type Result } from '@emdash/shared';
import { and, eq, isNotNull, isNull } from 'drizzle-orm';
import { getProvisionedWorkspaceBranch } from '@core/features/workspaces/api/node/workspace-branch';
import type { MutationError } from '@core/primitives/wire/api/mutations';
import type { WorkspaceDeletionTombstone } from '@core/primitives/workspaces/api';
import type { AppDb, DrizzleTx } from '@core/services/app-db/node/db';
import type { WorkspaceRow } from '@core/services/app-db/node/schema';
import {
  createWorkspaceRegistry,
  liveWorkspaces,
  workspaceRegistryTable as workspaces,
} from './workspace-registry';

/**
 * Durable deletion tombstones on the workspaces mirror (ADR 0006). This module owns
 * the write recipe salvaged from the retired `enqueue-tombstoned` helper —
 * compile-before-mutate, atomic tombstone write, zero-rows-updated = duplicate — and
 * the tombstone-aware creation admission check. The tombstoned row *is* the queue;
 * nothing submits anywhere (the submit/revert half of the recipe died with the outbox).
 */

export type WorkspaceTombstoneOptions = WorkspaceDeletionTombstone['options'];

export type TombstoneWriteOutcome = 'tombstoned' | 'duplicate';

/**
 * Marks one live mirror row with a durable deletion tombstone. The payload — frozen
 * options plus the target record's UUID — is compiled fully before any mutation, and
 * the write is a single guarded UPDATE inside one transaction: zero rows updated means
 * the row is already tombstoned (or no longer live), which suppresses a UI double-fire
 * without overwriting the first click's frozen options.
 */
export function tombstoneWorkspaceRow(
  db: AppDb,
  input: {
    workspace: WorkspaceRow;
    options: WorkspaceTombstoneOptions;
    createdAt: number;
    precondition?(tx: DrizzleTx): MutationError | undefined;
  }
): Result<{ outcome: TombstoneWriteOutcome }, MutationError> {
  // Compile before mutation: authoring mistakes must not leave a partial tombstone.
  const tombstone: WorkspaceDeletionTombstone = {
    version: '1',
    targetRecordId: input.workspace.id,
    tombstonedAt: input.createdAt,
    options: input.options,
  };
  const registry = createWorkspaceRegistry(db, {
    now: () => new Date(input.createdAt).toISOString(),
  });
  let failure: MutationError | undefined;
  let changes = 0;
  db.transaction((tx) => {
    failure = input.precondition?.(tx);
    if (failure) return;
    changes = registry.tombstone(input.workspace.id, tombstone, tx);
  });
  if (failure) return err(failure);
  return ok({ outcome: changes === 0 ? 'duplicate' : 'tombstoned' });
}

export type WorkspaceTombstoneConflict = {
  type: 'workspace-tombstone-pending';
  workspaceId: string;
  message: string;
};

/**
 * Tombstone-aware creation admission (ADR 0006, spec §4): creating at a workspace,
 * path, or branch that carries a pending deletion tombstone is refused until the sweep
 * converges or the user untracks. A pure data check against the mirror — the successor
 * to the retired claim-conflict preflight. Identity-keyed by construction: tombstones
 * live on the row they target, so an untracked old row never blocks a new record.
 */
export function findWorkspaceTombstoneConflict(
  db: AppDb,
  target:
    | { kind: 'workspace'; workspaceId: string }
    | {
        kind: 'placement';
        location: NonNullable<WorkspaceRow['location']>;
        sshConnectionId: string | null;
        path?: string;
        branch?: string;
      }
): WorkspaceTombstoneConflict | undefined {
  if (target.kind === 'workspace') {
    const row = db
      .select()
      .from(workspaces)
      .where(and(eq(workspaces.id, target.workspaceId), pendingTombstones()))
      .limit(1)
      .get();
    if (!row) return undefined;
    return conflict(row.id, 'This workspace is pending deletion on its host.');
  }

  if (target.path === undefined && target.branch === undefined) return undefined;
  const hostIdentity =
    target.sshConnectionId === null
      ? isNull(workspaces.sshConnectionId)
      : eq(workspaces.sshConnectionId, target.sshConnectionId);
  const rows = db
    .select()
    .from(workspaces)
    .where(and(eq(workspaces.location, target.location), hostIdentity, pendingTombstones()))
    .all();
  for (const row of rows) {
    if (target.path !== undefined && row.path === target.path) {
      return conflict(row.id, `A deletion is still pending at ${target.path}.`);
    }
    const branch = getProvisionedWorkspaceBranch(row) ?? row.observedGit?.branch ?? null;
    if (target.branch !== undefined && branch === target.branch) {
      return conflict(row.id, `A deletion is still pending for branch "${target.branch}".`);
    }
  }
  return undefined;
}

/** Live rows carrying a pending deletion tombstone — the visible pending state. */
function pendingTombstones() {
  return and(liveWorkspaces(), isNotNull(workspaces.deletionTombstone));
}

function conflict(workspaceId: string, detail: string): WorkspaceTombstoneConflict {
  return {
    type: 'workspace-tombstone-pending',
    workspaceId,
    message: `${detail} Wait for it to complete, or untrack the workspace to release it.`,
  };
}
