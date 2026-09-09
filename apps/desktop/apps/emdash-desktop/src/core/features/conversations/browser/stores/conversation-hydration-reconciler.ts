import type { Disposable } from '@emdash/shared/concurrency';
import { systemClock, type Clock, type TimerHandle } from '@emdash/shared/scheduling';

export type ConversationSessionAdapter = {
  hydrateConversation(conversationId: string): Promise<void>;
  dehydrateConversation(conversationId: string): Promise<void>;
};

type Logger = {
  warn(message: string, data?: unknown): void;
};

type ConversationHydrationReconcilerOptions = {
  taskId: string;
  getConversations: () => ConversationSessionAdapter | undefined;
  log: Logger;
  clock?: Clock;
};

type SessionState = 'stopped' | 'starting' | 'running' | 'stopping';

export const DEHYDRATE_RETRY_DELAY_MS = 500;

type Entry = {
  desired: boolean;
  state: SessionState;
  dehydrateRetryTimer: TimerHandle | null;
};

export class ConversationHydrationReconciler implements Disposable {
  private readonly taskId: string;
  private readonly getConversations: () => ConversationSessionAdapter | undefined;
  private readonly log: Logger;
  private readonly clock: Clock;
  private readonly entries = new Map<string, Entry>();
  private disposed = false;

  constructor({ taskId, getConversations, log, clock }: ConversationHydrationReconcilerOptions) {
    this.taskId = taskId;
    this.getConversations = getConversations;
    this.log = log;
    this.clock = clock ?? systemClock;
  }

  sync(openConversationIds: Iterable<string>): void {
    if (this.disposed) return;

    const desired = new Set(openConversationIds);
    const ids = new Set([...this.entries.keys(), ...desired]);

    for (const id of ids) {
      const entry = this.getOrCreateEntry(id);
      entry.desired = desired.has(id);
      if (entry.desired) this.clearDehydrateRetry(entry);
      this.reconcile(id, entry);
      this.cleanupIfIdle(id, entry);
    }
  }

  dispose(): void {
    this.disposed = true;
    for (const [id, entry] of this.entries) {
      this.clearDehydrateRetry(entry);
      entry.desired = false;
      this.reconcile(id, entry);
      this.cleanupIfIdle(id, entry);
    }
  }

  private getOrCreateEntry(id: string): Entry {
    const existing = this.entries.get(id);
    if (existing) return existing;
    const entry: Entry = { desired: false, state: 'stopped', dehydrateRetryTimer: null };
    this.entries.set(id, entry);
    return entry;
  }

  private reconcile(id: string, entry: Entry): void {
    if (entry.desired && entry.state === 'stopped') {
      void this.hydrate(id, entry);
      return;
    }
    if (!entry.desired && entry.state === 'running') {
      void this.dehydrate(id, entry);
    }
  }

  private async hydrate(id: string, entry: Entry): Promise<void> {
    const conversations = this.getConversations();
    if (!conversations) return;

    entry.state = 'starting';
    try {
      await conversations.hydrateConversation(id);
    } catch (error) {
      entry.state = 'stopped';
      this.log.warn('ConversationHydrationReconciler: failed to hydrate conversation', {
        taskId: this.taskId,
        conversationId: id,
        error,
      });
      this.cleanupIfIdle(id, entry);
      return;
    }

    entry.state = 'running';
    // intent may have flipped while we awaited — tear down if no longer wanted
    if (entry.desired) return;
    void this.dehydrate(id, entry, 'stale-hydrate');
  }

  private async dehydrate(
    id: string,
    entry: Entry,
    reason: 'sync' | 'stale-hydrate' = 'sync'
  ): Promise<void> {
    const conversations = this.getConversations();
    if (!conversations) {
      entry.state = 'stopped';
      this.cleanupIfIdle(id, entry);
      return;
    }

    entry.state = 'stopping';
    try {
      await conversations.dehydrateConversation(id);
    } catch (error) {
      entry.state = 'running';
      this.log.warn(
        reason === 'stale-hydrate'
          ? 'ConversationHydrationReconciler: failed to dehydrate stale conversation'
          : 'ConversationHydrationReconciler: failed to dehydrate conversation',
        {
          taskId: this.taskId,
          conversationId: id,
          error,
        }
      );
      if (!entry.desired) this.scheduleDehydrateRetry(id, entry);
      return;
    }

    entry.state = 'stopped';
    this.clearDehydrateRetry(entry);
    // intent may have flipped while we awaited — restart if wanted again
    if (entry.desired) {
      this.reconcile(id, entry);
      return;
    }
    this.cleanupIfIdle(id, entry);
  }

  private cleanupIfIdle(id: string, entry: Entry): void {
    if (entry.desired || entry.state !== 'stopped') return;
    this.clearDehydrateRetry(entry);
    this.entries.delete(id);
  }

  private scheduleDehydrateRetry(id: string, entry: Entry): void {
    if (this.disposed || entry.dehydrateRetryTimer) return;
    entry.dehydrateRetryTimer = this.clock.schedule(DEHYDRATE_RETRY_DELAY_MS, () => {
      entry.dehydrateRetryTimer = null;
      if (this.entries.get(id) !== entry || entry.desired) return;
      this.reconcile(id, entry);
      this.cleanupIfIdle(id, entry);
    });
  }

  private clearDehydrateRetry(entry: Entry): void {
    void entry.dehydrateRetryTimer?.dispose();
    entry.dehydrateRetryTimer = null;
  }
}
