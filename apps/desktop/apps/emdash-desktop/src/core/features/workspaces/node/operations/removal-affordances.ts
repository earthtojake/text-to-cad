import { hostRef, LOCAL_HOST_REF, type HostRef } from '@emdash/core/primitives/host/api';
import { createWorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import type { WorkspaceRow } from '@core/services/app-db/node/schema';
import type { ReconcileSweepHandle } from '@core/services/reconcile-sweep/node/reconcile-sweep-service';

/**
 * The needs-attention affordances for a pending deletion stopped by a terminal
 * removal failure (ADR 0006): Retry re-arms the sweep, Untrack-anyway abandons the
 * intent client-side. Operation functions — the wire controller delegates here.
 */

/**
 * Retry affordance: durably advances the tombstone's attempt epoch — the recorded
 * terminal stop goes inert on the row itself, so registry sync and app restarts can
 * never resurrect it — then resets the sweep's backoff and sweeps the host now, so
 * exactly one fresh attempt runs. No-op without a pending tombstone.
 */
export function retryWorkspaceRemoval(
  db: AppDb,
  sweep: ReconcileSweepHandle,
  workspaceId: string
): void {
  const registry = createWorkspaceRegistry(db);
  const row = registry.getLive(workspaceId);
  if (!row?.deletionTombstone) return;
  registry.retryTombstone(workspaceId);
  appDbPokes.workspaces.poke({ workspaceId });
  const host = decodeWorkspaceHost(row);
  if (host !== null) sweep.retry('workspaces', host, workspaceId);
}

/**
 * "Untrack anyway" affordance: abandons the pending deletion — the durable untrack
 * purges the tombstoned mirror row client-side and keeps sync from resurrecting it
 * while the host artifacts live on. No-op without a pending tombstone.
 */
export function abandonWorkspaceRemoval(
  db: AppDb,
  sweep: ReconcileSweepHandle,
  workspaceId: string
): void {
  const registry = createWorkspaceRegistry(db);
  const row = registry.getLive(workspaceId);
  if (!row?.deletionTombstone) return;
  registry.untrack([workspaceId], new Date().toISOString());
  sweep.drop('workspaces', workspaceId);
  appDbPokes.workspaces.poke({ workspaceId });
}

/** Identity-lost rows (deleted SSH connection, no location) decode to null, never local. */
export function decodeWorkspaceHost(
  row: Pick<WorkspaceRow, 'location' | 'sshConnectionId'>
): HostRef | null {
  if (row.location === 'local' && row.sshConnectionId === null) return LOCAL_HOST_REF;
  if (row.location === 'remote' && row.sshConnectionId !== null) {
    return hostRef('remote', row.sshConnectionId);
  }
  return null;
}
