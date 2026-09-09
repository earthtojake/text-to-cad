import {
  hostRefKey,
  isLocalHostRef,
  type HostRef,
  type SerializedHostRef,
} from '@emdash/core/primitives/host/api';
import type {
  ConversationType,
  CreateConversationInput,
} from '@emdash/core/runtimes/conversations/api';
import { and, eq, isNull } from 'drizzle-orm';
import { conversationIdRegimeFor } from '@core/features/conversations/api/node/host-index';
import {
  conversationRegistryTable as conversations,
  liveConversations,
} from '@core/features/conversations/api/node/registry';
import type { ConversationsRuntimeBroker } from '@core/features/conversations/api/runtime-adapter';
import type { AppDb } from '@core/services/app-db/node/db';
import { AppDbKeyValueStore } from '@core/services/app-db/node/key-value-store';
import type { ConversationRow } from '@core/services/app-db/node/schema';

export interface ConversationBackfillServiceOptions {
  db: AppDb;
  runtimes: ConversationsRuntimeBroker;
  onError?: (context: string, error: unknown) => void;
}

type BackfillFlags = Record<SerializedHostRef, number>;

/**
 * Upgrade backfill (spec §8): history created before host residency exists only as reshaped
 * client rows, so each becomes an idempotent `create` against its host's index, carrying
 * the observation seed values as the initial record state. One sweep per host, tracked by
 * a per-host completed flag; the obligation never expires and never blocks anything —
 * a host never seen again simply leaves its rows as kept, stale observations.
 *
 * Ordering: run before the sync service attaches the host, so the first missing-sweep
 * already sees the backfilled records instead of transiently marking legacy rows missing.
 */
export class ConversationBackfillService {
  private readonly flags: AppDbKeyValueStore<BackfillFlags>;

  constructor(private readonly options: ConversationBackfillServiceOptions) {
    this.flags = new AppDbKeyValueStore<BackfillFlags>(options.db, 'conversation-backfill');
  }

  /** Never throws: failures leave the flag unset so the next boot/connect resumes. */
  async backfillHost(host: HostRef): Promise<void> {
    try {
      await this.run(host);
    } catch (error) {
      this.options.onError?.(`conversation backfill (${hostRefKey(host)})`, error);
    }
  }

  private async run(host: HostRef): Promise<void> {
    const flagKey = hostRefKey(host);
    if ((await this.flags.get(flagKey)) !== null) return;

    const client = await this.options.runtimes.client(host);
    if (!client.success) return;
    const index = client.data.conversations;

    // Every live row of this host is replayed: `create` is a no-op success when the
    // immutable field set matches, so post-upgrade host-first rows pass through cleanly.
    for (const row of this.loadHostRows(host)) {
      const seed = compileBackfillCreateInput(row);
      if (seed === undefined) continue; // Incomplete legacy seed; stays a stale observation.
      const created = await index.create(seed);
      if (!created.success) {
        // Divergent immutable identity on the host: the host record wins; never fought.
        this.options.onError?.(
          `conversation backfill create (${row.id})`,
          new Error(created.error.message)
        );
        continue;
      }
      if (row.providerSessionId) {
        // Seed the last-observed resume handle so convergence does not null it out.
        await index.reports.providerSessionId({
          conversationId: row.id,
          providerSessionId: row.providerSessionId,
        });
      }
    }

    // Only a fully-walked sweep sets the flag; a transport throw above resumes later.
    await this.flags.setOrThrow(flagKey, Date.now());
  }

  private loadHostRows(host: HostRef): ConversationRow[] {
    const local = isLocalHostRef(host);
    return this.options.db
      .select()
      .from(conversations)
      .where(
        and(
          liveConversations(),
          eq(conversations.location, local ? 'local' : 'remote'),
          local ? isNull(conversations.sshConnectionId) : eq(conversations.sshConnectionId, host.id)
        )
      )
      .all();
  }
}

/**
 * Compiles a client row's cached observation into the host `create` seed. Rows missing
 * required immutable fields (possible for very old pre-reshape data) are skipped: they
 * keep serving reads as stale cached observations, consistent with the orphan policy.
 */
export function compileBackfillCreateInput(
  row: Pick<
    ConversationRow,
    | 'id'
    | 'provider'
    | 'type'
    | 'cwd'
    | 'workspacePath'
    | 'idRegime'
    | 'createdAt'
    | 'title'
    | 'config'
  >
): CreateConversationInput | undefined {
  const type = row.type === 'acp' || row.type === 'pty' ? (row.type as ConversationType) : null;
  const cwd = row.cwd ?? row.workspacePath;
  const createdAt = Date.parse(row.createdAt);
  if (!row.provider || type === null || !cwd || Number.isNaN(createdAt)) return undefined;
  return {
    conversationId: row.id,
    provider: row.provider,
    type,
    cwd,
    workspacePath: row.workspacePath ?? cwd,
    idRegime: row.idRegime ?? conversationIdRegimeFor(type),
    createdAt,
    title: row.title,
    config: row.config ?? {},
  };
}
