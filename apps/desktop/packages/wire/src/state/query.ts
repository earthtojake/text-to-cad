import { isDeepEqual, type Unsubscribe } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import { systemClock, type Clock, type TimerHandle } from '@emdash/shared/scheduling';
import {
  StateNode,
  mergeMutationIds,
  type CommitOptions,
  type Readable,
  type Revision,
  type StateInstrumentation,
  type StateStatus,
} from './core';
import type { PokeSubscription } from './poke';

export type QueryLane = {
  run<T>(work: () => Promise<T> | T): Promise<T>;
};

export type QueryOptions<T> = {
  fetch: (context: { signal: AbortSignal }) => Promise<T>;
  pokes?: readonly PokeSubscription[];
  equals?: (left: T, right: T) => boolean;
  initial?: T;
  debounceMs?: number;
  revalidateEveryMs?: number;
  lane?: QueryLane;
  name?: string;
  onError?: (error: unknown) => void;
  clock?: Clock;
  /** Owns the query's poke subscriptions and timers; disposal ends the query. */
  scope: Scope;
  instrumentation?: StateInstrumentation;
  onObservedChange?: (observed: boolean) => void;
};

export interface Query<T> extends Readable<T | undefined> {
  invalidate(): void;
  refresh(options?: { mutationIds?: readonly string[] }): Promise<Revision>;
  settle(
    update: T | ((previous: T | undefined) => T),
    options?: { mutationIds?: readonly string[] }
  ): Revision;
  dispose(): void;
}

class QueryNode<T> extends StateNode<T | undefined> implements Query<T> {
  private readonly clock: Clock;
  private readonly unsubscribePokes: Unsubscribe[] = [];
  private initialized: boolean;
  private dirty = true;
  private disposed = false;
  private debounceTimer: TimerHandle | undefined;
  private revalidateTimer: TimerHandle | undefined;
  private controller: AbortController | undefined;
  private inFlight: Promise<Revision> | undefined;
  private queued: Promise<Revision> | undefined;
  /** Mutation ids that have not yet reached a committed snapshot. */
  private readonly pendingAckIds = new Set<string>();

  constructor(private readonly queryOptions: QueryOptions<T>) {
    super(queryOptions.initial, {
      equals: queryOptions.equals as (left: T | undefined, right: T | undefined) => boolean,
      name: queryOptions.name,
      instrumentation: queryOptions.instrumentation,
      onObservedChange: queryOptions.onObservedChange,
    });
    this.clock = queryOptions.clock ?? systemClock;
    this.initialized = queryOptions.initial !== undefined;
    this.snapshotValue = {
      ...this.snapshotValue,
      status: this.initialized ? 'live' : 'loading',
    };
    for (const poke of queryOptions.pokes ?? []) {
      this.unsubscribePokes.push(poke.subscribe(() => this.invalidate()));
    }
    queryOptions.scope.add(() => this.dispose());
  }

  invalidate(): void {
    if (this.disposed) return;
    this.dirty = true;
    if (this.initialized) this.publishStatus('stale');
    if (this.observed) this.scheduleDebounced();
  }

  refresh(options: { mutationIds?: readonly string[] } = {}): Promise<Revision> {
    this.assertActive();
    for (const id of options.mutationIds ?? []) this.pendingAckIds.add(id);
    this.clearDebounce();
    if (this.inFlight) {
      this.dirty = true;
      // Coalesced callers share one queued run; their ids accumulate in
      // pendingAckIds and ride the queued run's commit.
      this.queued ??= this.inFlight.then(
        () => this.runNow(),
        () => this.runNow()
      );
      return this.queued;
    }
    return this.runNow();
  }

  settle(
    update: T | ((previous: T | undefined) => T),
    options: { mutationIds?: readonly string[] } = {}
  ): Revision {
    this.assertActive();
    const previous = this.peek();
    if (typeof update === 'function' && previous === undefined) return this.currentRevision();
    const next =
      typeof update === 'function' ? (update as (previous: T | undefined) => T)(previous) : update;
    this.initialized = true;
    this.dirty = false;
    // The settled value is authoritative write-through: it reflects every
    // mutation whose refresh was requested before now, so drain pending acks.
    const drained = this.takePendingAcks([...this.pendingAckIds]);
    return this.commit(next, {
      status: 'live',
      mutationIds: mergeMutationIds(options.mutationIds, drained),
      observedAt: this.clock.now(),
    });
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    for (const unsubscribe of this.unsubscribePokes) unsubscribe();
    this.unsubscribePokes.length = 0;
    this.clearTimers();
    this.controller?.abort(new Error('Query disposed'));
  }

  protected override onObserved(): void {
    if (!this.initialized || this.dirty) this.scheduleDebounced();
    else this.armRevalidation();
  }

  protected override onUnobserved(): void {
    this.clearTimers();
  }

  private runNow(): Promise<Revision> {
    this.queued = undefined;
    this.clearDebounce();
    const startedAtRevision = this.currentSnapshot().revision;
    // Every pending id was requested before this fetch starts, so the fetched
    // value reflects those mutations and may acknowledge them.
    const captured = [...this.pendingAckIds];
    const run = (async () => {
      this.dirty = false;
      const controller = new AbortController();
      this.controller = controller;
      try {
        const fresh = await this.withLane(() =>
          this.queryOptions.fetch({ signal: controller.signal })
        );
        this.assertActive();
        if (this.currentSnapshot().revision > startedAtRevision) {
          // Superseded: the fetched value is discarded, but its mutation ids
          // must still reach a committed snapshot.
          return this.publishPendingAcks(captured);
        }
        this.initialized = true;
        return this.commit(fresh, {
          status: 'live',
          mutationIds: this.takePendingAcks(captured),
          observedAt: this.clock.now(),
        });
      } catch (error) {
        // Captured ids stay pending and attach to the next settling commit.
        this.dirty = false;
        this.publishStatus('error', { error });
        this.queryOptions.onError?.(error);
        throw error;
      } finally {
        if (this.controller === controller) this.controller = undefined;
        this.inFlight = undefined;
        this.armRevalidation();
        if (this.dirty && this.observed && !this.queued) this.scheduleDebounced();
      }
    })();
    this.inFlight = run;
    return run;
  }

  private takePendingAcks(captured: readonly string[]): readonly string[] | undefined {
    const deliver = captured.filter((id) => this.pendingAckIds.has(id));
    for (const id of deliver) this.pendingAckIds.delete(id);
    return deliver.length > 0 ? deliver : undefined;
  }

  private publishPendingAcks(captured: readonly string[]): Revision {
    const deliver = this.takePendingAcks(captured);
    if (!deliver) return this.currentRevision();
    const current = this.currentSnapshot();
    return this.commit(current.value, {
      mutationIds: mergeMutationIds(current.mutationIds, deliver),
    });
  }

  private publishStatus(status: StateStatus, options: Pick<CommitOptions, 'error'> = {}): void {
    this.commit(this.peek(), {
      status,
      error: options.error,
    });
  }

  private scheduleDebounced(): void {
    if (this.disposed) return;
    this.clearDebounce();
    this.debounceTimer = this.clock.schedule(
      this.queryOptions.debounceMs ?? 0,
      () => {
        this.debounceTimer = undefined;
        if (!this.dirty || !this.observed || this.disposed) return;
        void this.refresh().catch(() => {});
      },
      { unref: true }
    );
  }

  private armRevalidation(): void {
    const interval = this.queryOptions.revalidateEveryMs;
    if (!interval || !this.observed || this.disposed) return;
    this.revalidateTimer?.dispose();
    this.revalidateTimer = this.clock.schedule(
      interval,
      () => {
        this.revalidateTimer = undefined;
        if (!this.observed || this.disposed) return;
        this.dirty = true;
        void this.refresh().catch(() => {});
      },
      { unref: true }
    );
  }

  private clearTimers(): void {
    this.clearDebounce();
    this.revalidateTimer?.dispose();
    this.revalidateTimer = undefined;
  }

  private clearDebounce(): void {
    this.debounceTimer?.dispose();
    this.debounceTimer = undefined;
  }

  private withLane<R>(work: () => Promise<R>): Promise<R> {
    return this.queryOptions.lane ? this.queryOptions.lane.run(work) : work();
  }

  private currentRevision(): Revision {
    return {
      nodeId: this.id,
      revision: this.currentSnapshot().revision,
      generation: this.currentSnapshot().generation,
      mutationIds: this.currentSnapshot().mutationIds,
    };
  }

  private assertActive(): void {
    if (this.disposed) throw new Error('Query is disposed');
  }
}

export function query<T>(options: QueryOptions<T>): Query<T> {
  return new QueryNode({
    ...options,
    equals: options.equals ?? isDeepEqual,
  });
}
