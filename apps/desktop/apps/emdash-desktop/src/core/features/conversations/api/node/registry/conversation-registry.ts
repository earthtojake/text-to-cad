import { and, eq, inArray, isNull, type SQL } from 'drizzle-orm';
import {
  tombstoneAttemptEpoch,
  type TombstoneTerminalStop,
} from '@core/primitives/reconcile/api/tombstone-attempts';
import type { AppDb, DrizzleTx } from '@core/services/app-db/node/db';
import {
  conversations,
  type ConversationInsert,
  type ConversationRow,
} from '@core/services/app-db/node/schema';

/**
 * Observation columns: cached host record fields (spec §5.1). The host wins wholesale —
 * a refresh overwrites cached fields unconditionally and stamps `lastObservedAt`. Source
 * host identity (`location`/`sshConnectionId`) is refreshable: a duplicated id across hosts
 * means a cloned host state dir, and the last-observed host wins.
 */
type ConversationObservation = Readonly<
  Partial<
    Pick<
      ConversationInsert,
      | 'title'
      | 'provider'
      | 'type'
      | 'config'
      | 'cwd'
      | 'workspacePath'
      | 'providerSessionId'
      | 'idRegime'
      | 'lastSessionActivityAt'
      | 'observedStatus'
      | 'createdAt'
      | 'updatedAt'
      | 'location'
      | 'sshConnectionId'
    >
  > & { lastObservedAt: string }
>;

/** Annotation columns: client-owned, never present in host payloads (spec §5.1). */
type ConversationAnnotation = Partial<
  Pick<ConversationInsert, 'taskId' | 'projectId' | 'isInitialConversation' | 'agentStatusSeen'>
>;

export type ConversationRegistryOptions = {
  now?: () => string;
};

/**
 * Sole writer for the client conversation registry (spec §5.2, ADR 0002 pattern). The
 * registry mirrors host conversation records (observations) and carries client-owned
 * annotations; it guards "who may touch the cache and the annotations," not conversation
 * truth — that lives in the host index. There is no local dirty state: observation columns
 * hold only host-acknowledged values.
 *
 * `agentStatus` stays outside the observation discipline: it converges from the live
 * session model as a device-local cache with its existing staleness resets.
 */
export class ConversationRegistry {
  private readonly now: () => string;

  constructor(
    private readonly db: AppDb,
    options: ConversationRegistryOptions = {}
  ) {
    this.now = options.now ?? (() => new Date().toISOString());
  }

  getLive(id: string, tx?: DrizzleTx): ConversationRow | undefined {
    const [row] = this.source(tx)
      .select()
      .from(conversations)
      .where(and(eq(conversations.id, id), liveConversations()))
      .limit(1)
      .all();
    return row;
  }

  /**
   * Claim a host-acknowledged conversation for this client. The live sync may have
   * adopted the host record before the create RPC unwinds, so conflict updates make
   * registration commutative with that adoption while preserving sync metadata.
   */
  register(values: ConversationInsert, tx?: DrizzleTx): ConversationRow {
    const now = this.now();
    const registered = {
      ...values,
      origin: 'registered' as const,
      createdAt: values.createdAt ?? now,
      updatedAt: values.updatedAt ?? now,
      untrackedAt: null,
    };
    return this.source(tx)
      .insert(conversations)
      .values(registered)
      .onConflictDoUpdate({
        target: conversations.id,
        set: {
          projectId: registered.projectId,
          taskId: registered.taskId,
          isInitialConversation: registered.isInitialConversation,
          title: registered.title,
          provider: registered.provider,
          type: registered.type,
          config: registered.config,
          cwd: registered.cwd,
          workspacePath: registered.workspacePath,
          providerSessionId: registered.providerSessionId,
          idRegime: registered.idRegime,
          lastSessionActivityAt: registered.lastSessionActivityAt,
          location: registered.location,
          sshConnectionId: registered.sshConnectionId,
          origin: 'registered',
          updatedAt: registered.updatedAt,
          untrackedAt: null,
        },
      })
      .returning()
      .get();
  }

  /**
   * Mirror a host record without client-owned links. If registration won the race,
   * preserve that row wholesale instead of clearing its annotations.
   */
  adopt(
    values: Omit<ConversationInsert, 'taskId' | 'projectId' | 'origin'>,
    tx?: DrizzleTx
  ): ConversationRow {
    const now = this.now();
    const source = this.source(tx);
    const adopted = source
      .insert(conversations)
      .values({
        ...values,
        taskId: null,
        projectId: null,
        origin: 'adopted',
        createdAt: values.createdAt ?? now,
        updatedAt: values.updatedAt ?? now,
        untrackedAt: null,
      })
      .onConflictDoNothing({ target: conversations.id })
      .returning()
      .get();
    if (adopted !== undefined) return adopted;

    const existing = source
      .select()
      .from(conversations)
      .where(eq(conversations.id, values.id))
      .get();
    if (existing === undefined) {
      throw new Error(`Conversation '${values.id}' disappeared during adoption`);
    }
    return existing;
  }

  /** Observation columns only, stamped with the host-side observation time; live rows only. */
  refresh(id: string, observation: ConversationObservation, tx?: DrizzleTx): number {
    return this.source(tx)
      .update(conversations)
      .set(observation)
      .where(and(eq(conversations.id, id), liveConversations()))
      .run().changes;
  }

  /** Annotation columns only; annotating untracked rows is allowed. */
  annotate(id: string, annotation: ConversationAnnotation, tx?: DrizzleTx): number {
    return this.source(tx)
      .update(conversations)
      .set(annotation)
      .where(eq(conversations.id, id))
      .run().changes;
  }

  /**
   * Marks one live row with a durable deletion tombstone (ADR 0006). Atomic and
   * first-writer-wins: the guard on a null `deletionTombstone` makes zero rows updated
   * mean "already tombstoned" (or no longer live), so a UI double-fire never overwrites
   * the first write. The row stays live — the visible pending state.
   */
  tombstone(
    id: string,
    tombstone: NonNullable<ConversationRow['deletionTombstone']>,
    tx?: DrizzleTx
  ): number {
    return this.source(tx)
      .update(conversations)
      .set({ deletionTombstone: tombstone, updatedAt: this.now() })
      .where(
        and(eq(conversations.id, id), liveConversations(), isNull(conversations.deletionTombstone))
      )
      .run().changes;
  }

  /**
   * The durable half of the Retry affordance (ADR 0006): advances the tombstone's
   * attempt epoch on the row itself, so the recorded terminal stop from the previous
   * epoch goes inert — durably. A sync delivery or an app restart can never resurrect
   * the cleared stop. Zero rows updated means no live tombstoned row — a no-op.
   */
  retryTombstone(id: string, tx?: DrizzleTx): number {
    const row = this.getLive(id, tx);
    const tombstone = row?.deletionTombstone;
    if (!row || !tombstone) return 0;
    return this.source(tx)
      .update(conversations)
      .set({
        deletionTombstone: { ...tombstone, attemptEpoch: tombstoneAttemptEpoch(tombstone) + 1 },
        updatedAt: this.now(),
      })
      .where(and(eq(conversations.id, id), liveConversations()))
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
      .update(conversations)
      .set({
        deletionTombstone: { ...tombstone, terminalStop: stop },
        updatedAt: this.now(),
      })
      .where(and(eq(conversations.id, id), liveConversations()))
      .run().changes;
  }

  untrack(ids: readonly string[], untrackedAt: string, tx?: DrizzleTx): number {
    if (ids.length === 0) return 0;
    return this.source(tx)
      .update(conversations)
      .set({ untrackedAt })
      .where(and(inArray(conversations.id, [...ids]), liveConversations()))
      .run().changes;
  }

  revertUntrack(ids: readonly string[], tx?: DrizzleTx): number {
    if (ids.length === 0) return 0;
    return this.source(tx)
      .update(conversations)
      .set({ untrackedAt: null })
      .where(inArray(conversations.id, [...ids]))
      .run().changes;
  }

  purge(ids: readonly string[], tx?: DrizzleTx): number {
    if (ids.length === 0) return 0;
    const source = this.source(tx);
    const tracked = source
      .select({ id: conversations.id })
      .from(conversations)
      .where(and(inArray(conversations.id, [...ids]), liveConversations()))
      .all();
    if (tracked.length > 0) {
      throw new Error(
        `Registry rows must be untracked before purge: ${tracked.map(({ id }) => id).join(', ')}`
      );
    }
    return source
      .delete(conversations)
      .where(inArray(conversations.id, [...ids]))
      .run().changes;
  }

  private source(tx?: DrizzleTx): AppDb {
    // AppDb and its transaction expose the same query-builder surface used by
    // this module; Drizzle does not publish a shared structural type for it.
    return (tx ?? this.db) as unknown as AppDb;
  }
}

export function createConversationRegistry(
  db: AppDb,
  options?: ConversationRegistryOptions
): ConversationRegistry {
  return new ConversationRegistry(db, options);
}

export function liveConversations(): SQL {
  return isNull(conversations.untrackedAt);
}

/**
 * "Annotated" for the missing sweep = has a task link (spec §5.4) — stricter than
 * workspaces; a conversation record has no recreate-from-provenance value.
 */
export function isAnnotatedConversation(row: { taskId: string | null }): boolean {
  return row.taskId !== null;
}

/** Read-side table export. All mutations must go through `ConversationRegistry`. */
export const conversationRegistryTable = conversations;
