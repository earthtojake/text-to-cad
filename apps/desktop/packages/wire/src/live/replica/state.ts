import { createEmitter, type Unsubscribe } from '@emdash/shared';
import type { Logger } from '@emdash/shared/logger';
import type { Clock } from '@emdash/shared/scheduling';
import type { z } from 'zod';
import type { LiveCursor, LiveSnapshot, LiveSource, LiveUpdate } from '../../api/channel';
import type { LiveClientHandle } from '../../api/client';
import type { WireInstrumentation } from '../../api/instrumentation';
import { resyncRetry, type LiveResyncFailurePolicy } from '../follower';
import { LiveStateClient, type LiveChangeMeta } from '../state';
import { LiveStateWaiters } from '../state/waiters';
import { createPlainStore, type StateStore } from './store';

export type ReplicaStateOptions<T> = {
  store?: StateStore<T>;
  schema?: z.ZodType<T>;
  onChange?: (value: T, meta: LiveChangeMeta) => void;
  /** Resync failure policy; production replicas retry until success or dispose. */
  onResyncFailed?: LiveResyncFailurePolicy;
  instrumentation?: WireInstrumentation;
  logger?: Logger;
  clock?: Clock;
};

type ReplicaStateChange<T> = {
  value: T;
  meta: LiveChangeMeta;
};

export class ReplicaState<T> implements LiveSource {
  readonly ready: Promise<void>;

  private readonly emitter = createEmitter<LiveUpdate>();
  private readonly changeEmitter = createEmitter<ReplicaStateChange<T>>();
  private readonly client: LiveStateClient<T>;
  private readonly store: StateStore<T>;
  private readonly localWaiters: LiveStateWaiters;
  private readonly detachPromise: Promise<Unsubscribe>;
  private localGeneration = nextGeneration();
  private localSequence = 0;
  private upstreamBase: LiveCursor | undefined;
  private disposed = false;

  constructor(
    private readonly handle: LiveClientHandle<T>,
    private readonly deps: ReplicaStateOptions<T> = {}
  ) {
    this.store = deps.store ?? createPlainStore<T>();
    this.localWaiters = new LiveStateWaiters(() => this.localCursor(), { clock: deps.clock });
    this.client = new LiveStateClient<T>(
      deps.schema,
      () => handle.snapshot(),
      (value, meta) => this.handleChange(value, meta),
      {
        instrumentation: deps.instrumentation,
        logger: deps.logger,
        clock: deps.clock,
        topic: handle.topic,
        label: 'replica model',
        store: this.store,
        onResyncFailed: deps.onResyncFailed ?? resyncRetry(),
        onSeeded: () => this.handleSeeded(),
        onApplied: (update) => this.handleApplied(update),
      }
    );
    this.detachPromise = handle.attach((update) => this.applyUpdate(update), {
      onReattach: () => this.client.invalidate(),
    });
    this.ready = Promise.all([handle.snapshot(), this.detachPromise]).then(([snapshot]) =>
      this.seed(snapshot)
    );
  }

  current(): T {
    return this.store.current();
  }

  get cursor(): LiveCursor | undefined {
    return this.client.cursor;
  }

  /** True while a resync is needed or in flight, including after a give-up. */
  get stale(): boolean {
    return this.client.stale;
  }

  seed(snapshot: LiveSnapshot<T>): void {
    this.upstreamBase = {
      generation: snapshot.generation,
      sequence: snapshot.sequence,
    };
    this.client.seed(snapshot);
  }

  applyUpdate(update: LiveUpdate): void {
    this.client.applyUpdate(update);
  }

  refresh(): Promise<void> {
    return this.client.refresh();
  }

  async snapshot(): Promise<LiveSnapshot<unknown>> {
    await this.ready;
    return {
      generation: this.localGeneration,
      sequence: this.localSequence,
      timestamp: Date.now(),
      data: structuredClone(this.store.serialize()),
    };
  }

  subscribe(cb: (update: LiveUpdate) => void): Unsubscribe {
    return this.emitter.subscribe(cb);
  }

  onChange(cb: (value: T, meta: LiveChangeMeta) => void): Unsubscribe {
    return this.changeEmitter.subscribe(({ value, meta }) => cb(value, meta));
  }

  waitForCursor(target: LiveCursor, timeoutMs = 15_000): Promise<void> {
    if (this.disposed) return Promise.reject(new Error('ReplicaState disposed'));
    return this.client.waitForCursor(target, timeoutMs);
  }

  waitForLocalCursor(target: LiveCursor, timeoutMs = 15_000): Promise<void> {
    if (this.disposed) return Promise.reject(new Error('ReplicaState disposed'));
    return this.localWaiters.waitForCursor(target, timeoutMs);
  }

  waitForMutation(mutationId: string, timeoutMs = 15_000): Promise<void> {
    if (this.disposed) return Promise.reject(new Error('ReplicaState disposed'));
    return this.client.waitForMutation(mutationId, timeoutMs);
  }

  localCursorFor(upstream: LiveCursor): LiveCursor {
    const current = this.cursor;
    if (
      !current ||
      !this.upstreamBase ||
      current.generation !== upstream.generation ||
      this.upstreamBase.generation !== upstream.generation
    ) {
      return this.localCursor();
    }

    return {
      generation: this.localGeneration,
      sequence: Math.max(0, upstream.sequence - this.upstreamBase.sequence),
    };
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    this.localWaiters.rejectAll(new Error('ReplicaState disposed'));
    this.client.dispose();
    this.emitter.clear();
    this.changeEmitter.clear();
    (await this.detachPromise)();
  }

  /** Renumbers the local generation before the seed change fans out. */
  private handleSeeded(): void {
    this.localGeneration = nextGeneration(this.localGeneration);
    this.localSequence = 0;
  }

  /** Re-emits the applied update under local numbering before the change fans out. */
  private handleApplied(update: LiveUpdate): void {
    const baseSequence = this.localSequence;
    this.localSequence += 1;
    this.emitter.emit({
      generation: this.localGeneration,
      baseSequence,
      sequence: this.localSequence,
      timestamp: update.timestamp,
      delta: update.delta,
      mutationIds: update.mutationIds,
    });
  }

  private handleChange(value: T, meta: LiveChangeMeta): void {
    this.deps.onChange?.(value, meta);
    this.changeEmitter.emit({ value, meta });
    this.localWaiters.flushCursorWaiters();
  }

  private localCursor(): LiveCursor {
    return {
      generation: this.localGeneration,
      sequence: this.localSequence,
    };
  }
}

function nextGeneration(previous = 0): number {
  return Math.max(Date.now(), previous + 1);
}
