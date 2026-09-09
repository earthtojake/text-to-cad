import type {
  ConversationRecord,
  ConversationRecords,
} from '@emdash/core/runtimes/conversations/api';
import { and, eq, isNull } from 'drizzle-orm';
import {
  conversationRegistryTable as conversations,
  createConversationRegistry,
  isAnnotatedConversation,
  liveConversations,
  type ConversationRegistry,
} from '@core/features/conversations/api/node/registry';
import type { ConversationConfig } from '@core/primitives/conversations/api';
import type { AppDb, DrizzleTx } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import type { ConversationRow } from '@core/services/app-db/node/schema';

export type ConversationHostIdentity = Readonly<{
  location: 'local' | 'remote';
  sshConnectionId: string | null;
}>;

export interface ApplyConversationSnapshotInput {
  db: AppDb;
  host: ConversationHostIdentity;
  records: ConversationRecords;
  /** Host-side observation time; defaults to now. */
  observedAt?: string;
}

export interface ApplyConversationSnapshotResult {
  adopted: number;
  refreshed: number;
  markedMissing: number;
  untracked: number;
  /** Tombstoned rows whose host record this delivery confirmed gone (ADR 0006). */
  purgedTombstones: number;
}

/**
 * Converges the client conversation registry toward one host's index (spec §5.3): the
 * authoritative snapshot applies in a single transaction through registry verbs — refresh
 * matches, adopt unknowns, sweep unmatched rows through the missing rules. Scope is per
 * host; the cache is never the authority (`conv.cache-not-authority`), so observations
 * overwrite wholesale. Callers must only invoke this after a *successful* index read: an
 * unreachable host marks nothing missing (positive assertion, spec §5.4).
 */
export async function applyConversationSnapshot(
  input: ApplyConversationSnapshotInput
): Promise<ApplyConversationSnapshotResult> {
  const now = new Date().toISOString();
  const registry = createConversationRegistry(input.db, { now: () => now });
  const result = input.db.transaction((tx) =>
    applyConversationSnapshotTx(tx, input, registry, now)
  );
  appDbPokes.conversations.poke({});
  return result;
}

function applyConversationSnapshotTx(
  tx: DrizzleTx,
  input: ApplyConversationSnapshotInput,
  registry: ConversationRegistry,
  now: string
): ApplyConversationSnapshotResult {
  const observedAt = input.observedAt ?? now;
  const hostRows = loadLiveHostRows(tx, input.host);
  const counts: ApplyConversationSnapshotResult = {
    adopted: 0,
    refreshed: 0,
    markedMissing: 0,
    untracked: 0,
    purgedTombstones: 0,
  };

  const seen = new Set<string>();
  for (const record of Object.values(input.records)) {
    seen.add(record.conversationId);
    // Matching is a primary-key lookup on the emdash conversation id — no path matching.
    // A row cached from another host converges here too: source host is a refreshable
    // field, and the last-observed host wins on duplicated ids (spec §5).
    const existing = registry.getLive(record.conversationId, tx);
    if (existing === undefined) {
      registry.adopt(
        {
          id: record.conversationId,
          ...observationFor(record, input.host, observedAt),
          createdAt: isoFromMs(record.createdAt),
        },
        tx
      );
      counts.adopted += 1;
      continue;
    }
    registry.refresh(record.conversationId, observationFor(record, input.host, observedAt), tx);
    counts.refreshed += 1;
  }

  for (const row of hostRows) {
    if (seen.has(row.id)) continue;
    // Purge-on-mirror-confirmed-gone (ADR 0006): the delivery is the host's full
    // index, so a live tombstoned row absent from it has converged — the pending
    // deletion completed (or the record never existed). The untrack is the purge;
    // annotation never keeps a row the user already deleted visible as missing.
    if (row.deletionTombstone !== null) {
      registry.untrack([row.id], now, tx);
      counts.purgedTombstones += 1;
      continue;
    }
    if (isAnnotatedConversation(row)) {
      // Task-linked records stay visible in their task as missing until the user acts.
      registry.refresh(row.id, { observedStatus: 'missing', lastObservedAt: observedAt }, tx);
      counts.markedMissing += 1;
    } else {
      // Pure mirror entries follow the mirror.
      registry.untrack([row.id], now, tx);
      counts.untracked += 1;
    }
  }

  return counts;
}

function loadLiveHostRows(tx: DrizzleTx, host: ConversationHostIdentity): ConversationRow[] {
  const hostIdentity =
    host.sshConnectionId === null
      ? isNull(conversations.sshConnectionId)
      : eq(conversations.sshConnectionId, host.sshConnectionId);
  return tx
    .select()
    .from(conversations)
    .where(and(liveConversations(), eq(conversations.location, host.location), hostIdentity))
    .all();
}

function observationFor(
  record: ConversationRecord,
  host: ConversationHostIdentity,
  observedAt: string
) {
  return {
    title: record.title,
    provider: record.provider,
    type: record.type,
    // The index stores config opaquely (spec §3.2); its inner shape is client business,
    // written by this client family — parseable by the versioned column on read.
    config: record.config as ConversationConfig,
    cwd: record.cwd,
    workspacePath: record.workspacePath,
    providerSessionId: record.providerSessionId,
    idRegime: record.idRegime,
    lastSessionActivityAt: isoFromMs(record.lastSessionActivityAt),
    observedStatus: 'present' as const,
    createdAt: isoFromMs(record.createdAt),
    updatedAt: isoFromMs(record.updatedAt),
    location: host.location,
    sshConnectionId: host.sshConnectionId,
    lastObservedAt: observedAt,
  };
}

function isoFromMs(ms: number): string;
function isoFromMs(ms: number | null): string | null;
function isoFromMs(ms: number | null): string | null {
  return ms === null ? null : new Date(ms).toISOString();
}
