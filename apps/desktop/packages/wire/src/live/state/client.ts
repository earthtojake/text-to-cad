import type { Logger } from '@emdash/shared/logger';
import type { Clock } from '@emdash/shared/scheduling';
import type z from 'zod';
import type { LiveCursor, LiveSnapshot, LiveUpdate } from '../../api/channel';
import type { WireInstrumentation } from '../../api/instrumentation';
import { LiveFollower, type LiveResyncFailurePolicy } from '../follower';
import { createPlainStore, createStateMaterializer, type StateStore } from '../replica/store';
import { LiveStateWaiters } from './waiters';

export type LiveChangeMeta = { kind: 'seed' } | { kind: 'update'; mutationIds: string[] };

export type LiveStateClientOptions<T = unknown> = {
  /** Required policy deciding what happens when a resync refetch fails. */
  onResyncFailed: LiveResyncFailurePolicy;
  instrumentation?: WireInstrumentation;
  logger?: Logger;
  clock?: Clock;
  topic?: string;
  /** Label used in resync log messages; defaults to `live model`. */
  label?: string;
  store?: StateStore<T>;
  /** Composition hook invoked on every seed before change/waiter handling. */
  onSeeded?: () => void;
  /** Composition hook invoked on every applied update before change/waiter handling. */
  onApplied?: (update: LiveUpdate) => void;
};

export class LiveStateClient<T> {
  private readonly follower: LiveFollower<T>;
  private readonly waiters: LiveStateWaiters;
  private readonly store: StateStore<T>;
  private readonly onChange: (value: T, meta: LiveChangeMeta) => void;
  private readonly onSeededHook: (() => void) | undefined;
  private readonly onAppliedHook: ((update: LiveUpdate) => void) | undefined;
  private disposed = false;

  constructor(
    schema: z.ZodType<T> | undefined,
    refetchSnapshot: () => Promise<LiveSnapshot<T>>,
    onChange: (value: T, meta: LiveChangeMeta) => void,
    options: LiveStateClientOptions<T>
  ) {
    const { store, label, onSeeded, onApplied, ...followerOptions } = options;
    this.store = store ?? createPlainStore<T>();
    this.onChange = onChange;
    this.onSeededHook = onSeeded;
    this.onAppliedHook = onApplied;
    this.waiters = new LiveStateWaiters(() => this.cursor, { clock: options.clock });
    this.follower = new LiveFollower(refetchSnapshot, createStateMaterializer(this.store, schema), {
      ...followerOptions,
      label: label ?? 'live model',
      onSeeded: () => this.handleSeeded(),
      onApplied: (update) => this.handleApplied(update),
    });
  }

  get cursor(): LiveCursor | undefined {
    return this.follower.cursor;
  }

  isReady(): boolean {
    return this.follower.isReady();
  }

  /** True while a resync is needed or in flight, including after a give-up. */
  get stale(): boolean {
    return this.follower.stale;
  }

  getSnapshot(): T | undefined {
    if (!this.follower.isReady()) return undefined;
    return this.store.current();
  }

  seed(snapshot: LiveSnapshot<T>): void {
    this.follower.seed(snapshot);
  }

  applyUpdate(update: LiveUpdate): void {
    this.follower.applyUpdate(update);
  }

  /** Resolves only once the follower is fresh; see `LiveFollower.refresh`. */
  refresh(): Promise<void> {
    return this.follower.refresh();
  }

  /** Triggers a resync without exposing a promise; failures follow the policy. */
  invalidate(): void {
    this.follower.invalidate();
  }

  /** Resolves when local state provably includes the given cursor. */
  waitForCursor(target: LiveCursor, timeoutMs = 15_000): Promise<void> {
    if (this.disposed) return Promise.reject(this.disposedError());
    return this.waiters.waitForCursor(target, timeoutMs);
  }

  /**
   * Resolves when an update tagged with this mutation ID is applied.
   * Any seed/resync also resolves because a fresh snapshot is authoritative.
   */
  waitForMutation(mutationId: string, timeoutMs = 15_000): Promise<void> {
    if (this.disposed) return Promise.reject(this.disposedError());
    return this.waiters.waitForMutation(mutationId, timeoutMs);
  }

  /** Rejects all pending waiters with a disposed error and stops resyncing. */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.waiters.rejectAll(this.disposedError());
    this.follower.dispose();
  }

  private handleSeeded(): void {
    this.onSeededHook?.();
    this.onChange(this.store.current(), { kind: 'seed' });
    this.waiters.flushCursorWaiters();
    this.waiters.flushAllMutationWaiters();
  }

  private handleApplied(update: LiveUpdate): void {
    this.onAppliedHook?.(update);
    this.onChange(this.store.current(), { kind: 'update', mutationIds: update.mutationIds ?? [] });
    this.waiters.flushCursorWaiters();
    this.waiters.flushMutationWaiters(update.mutationIds ?? []);
  }

  private disposedError(): Error {
    return new Error('LiveStateClient disposed');
  }
}
