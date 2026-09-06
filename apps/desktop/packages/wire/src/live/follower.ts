import { log as ambientLog, type Logger } from '@emdash/shared/logger';
import {
  retrySchedule,
  systemClock,
  type Clock,
  type RetrySchedule,
} from '@emdash/shared/scheduling';
import type { LiveCursor, LiveSnapshot, LiveUpdate } from '../api/channel';
import type { WireInstrumentation, WireResyncReason } from '../api/instrumentation';

export type LiveFollowerApplyResult =
  | { ok: true }
  | { ok: false; reason: WireResyncReason; details?: Record<string, unknown> };

export interface LiveMaterializer<T> {
  seed(snapshot: LiveSnapshot<T>): void;
  apply(update: LiveUpdate): LiveFollowerApplyResult;
}

export type LiveResyncFailureContext = {
  error: unknown;
  /** Consecutive failed resync attempts in the current stale episode, 1-based. */
  attempt: number;
  topic: string | undefined;
  label: string;
};

export type LiveResyncFailureDecision = { kind: 'retry'; delayMs: number } | { kind: 'give-up' };

/**
 * Decides what a follower does when a resync snapshot refetch fails. Every
 * follower must be constructed with one; wire ships `resyncRetry` and
 * `resyncMarkStale` so callers pick a policy rather than hand-roll one.
 */
export type LiveResyncFailurePolicy = (
  context: LiveResyncFailureContext
) => LiveResyncFailureDecision;

const DEFAULT_RESYNC_RETRY_DELAYS_MS = [250, 1_000, 2_500, 5_000];

/**
 * Retry the snapshot refetch on a bounded backoff until it succeeds or the
 * follower is disposed. The default schedule repeats its last delay forever.
 */
export function resyncRetry(options: { schedule?: RetrySchedule } = {}): LiveResyncFailurePolicy {
  const schedule =
    options.schedule ??
    retrySchedule({ delaysMs: DEFAULT_RESYNC_RETRY_DELAYS_MS, repeatLast: true });
  return ({ attempt }) => {
    const delayMs = schedule.delayFor(attempt - 1);
    if (delayMs === undefined) return { kind: 'give-up' };
    return { kind: 'retry', delayMs };
  };
}

/**
 * Give up after a failed resync. The follower stays observably stale; the next
 * update or reattach triggers a fresh resync episode.
 */
export function resyncMarkStale(): LiveResyncFailurePolicy {
  return () => ({ kind: 'give-up' });
}

type LiveFollowerOptions = {
  instrumentation?: WireInstrumentation;
  logger?: Logger;
  clock?: Clock;
  topic?: string;
  label: string;
  onResyncFailed: LiveResyncFailurePolicy;
  onSeeded?: () => void;
  onApplied?: (update: LiveUpdate) => void;
};

type RefreshWaiter = {
  resolve: () => void;
  reject: (error: Error) => void;
};

export class LiveFollower<T> {
  private generation = -1;
  private sequence = -1;
  private needsResync = false;
  private resyncAttempt = 0;
  private loop: Promise<void> | undefined;
  private waiters: RefreshWaiter[] = [];
  private disposed = false;
  private readonly disposeController = new AbortController();
  private readonly clock: Clock;

  constructor(
    private readonly refetchSnapshot: () => Promise<LiveSnapshot<T>>,
    private readonly materializer: LiveMaterializer<T>,
    private readonly options: LiveFollowerOptions
  ) {
    this.clock = options.clock ?? systemClock;
  }

  get cursor(): LiveCursor | undefined {
    if (this.generation < 0) return undefined;
    return {
      generation: this.generation,
      sequence: this.sequence,
    };
  }

  isReady(): boolean {
    return this.generation >= 0;
  }

  /** True while a resync is needed or in flight, including after a give-up. */
  get stale(): boolean {
    return this.needsResync || this.loop !== undefined;
  }

  seed(snapshot: LiveSnapshot<T>): void {
    this.materializer.seed(snapshot);
    this.generation = snapshot.generation;
    this.sequence = snapshot.sequence;
    this.options.onSeeded?.();
  }

  applyUpdate(update: LiveUpdate): void {
    if (this.disposed) return;
    if (!this.isReady()) {
      this.triggerResync('sequence-gap', { reason: 'update-before-seed' });
      return;
    }

    if (update.generation !== this.generation) {
      this.triggerResync('generation', {
        local: this.generation,
        incoming: update.generation,
      });
      return;
    }

    if (update.baseSequence !== this.sequence) {
      this.triggerResync('sequence-gap', {
        expected: this.sequence,
        got: update.baseSequence,
      });
      return;
    }

    const applied = this.materializer.apply(update);
    if (!applied.ok) {
      this.triggerResync(applied.reason, applied.details ?? {});
      return;
    }

    this.sequence = update.sequence;
    this.options.onApplied?.(update);
  }

  /**
   * Forces a resync and resolves only once the follower is fresh: concurrent
   * calls coalesce onto the in-flight resync, and a resync trigger arriving
   * mid-flight re-runs the loop before resolution. Rejects when the failure
   * policy gives up or the follower is disposed.
   */
  refresh(): Promise<void> {
    if (this.disposed) return Promise.reject(this.disposedError());
    const promise = new Promise<void>((resolve, reject) => {
      this.waiters.push({ resolve, reject });
    });
    // Joining an in-flight resync is enough to become fresh; only start a new
    // refetch when no loop is running.
    if (!this.loop) this.needsResync = true;
    this.kick();
    return promise;
  }

  /**
   * Marks the follower stale and starts the resync loop without exposing a
   * promise. Failures flow through the resync failure policy, so no caller
   * can leak an unhandled rejection from this path.
   */
  invalidate(): void {
    if (this.disposed) return;
    this.needsResync = true;
    this.kick();
  }

  /** Cancels any resync retry loop and rejects pending refresh promises. */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.disposeController.abort(this.disposedError());
    this.settleWaiters((waiter) => waiter.reject(this.disposedError()));
  }

  protected triggerResync(reason: WireResyncReason, details: Record<string, unknown> = {}): void {
    const event = { topic: this.options.topic, reason, details };
    this.options.instrumentation?.resync?.(event);
    (this.options.logger ?? ambientLog).warn(`wire ${this.options.label} resyncing`, event);
    this.invalidate();
  }

  private kick(): void {
    if (this.loop) return;
    this.loop = this.runResyncLoop().finally(() => {
      this.loop = undefined;
    });
  }

  private async runResyncLoop(): Promise<void> {
    while (this.needsResync && !this.disposed) {
      this.needsResync = false;
      try {
        const snapshot = await this.refetchSnapshot();
        if (this.disposed) return;
        this.seed(snapshot);
        this.resyncAttempt = 0;
      } catch (error) {
        if (this.disposed) return;
        this.needsResync = true;
        this.resyncAttempt += 1;
        const failure: LiveResyncFailureContext = {
          error,
          attempt: this.resyncAttempt,
          topic: this.options.topic,
          label: this.options.label,
        };
        const decision = this.options.onResyncFailed(failure);
        this.options.instrumentation?.resyncFailed?.({
          topic: this.options.topic,
          error,
          attempt: this.resyncAttempt,
          willRetry: decision.kind === 'retry',
        });
        (this.options.logger ?? ambientLog).warn(`wire ${this.options.label} resync failed`, {
          topic: this.options.topic,
          attempt: this.resyncAttempt,
          willRetry: decision.kind === 'retry',
          error,
        });
        if (decision.kind === 'give-up') {
          this.resyncAttempt = 0;
          this.settleWaiters((waiter) => waiter.reject(toError(error)));
          return;
        }
        try {
          await this.clock.sleep(decision.delayMs, {
            signal: this.disposeController.signal,
            unref: true,
          });
        } catch {
          // Disposed while waiting to retry; dispose already settled waiters.
          return;
        }
      }
    }
    if (!this.disposed) this.settleWaiters((waiter) => waiter.resolve());
  }

  private settleWaiters(settle: (waiter: RefreshWaiter) => void): void {
    const waiters = this.waiters;
    this.waiters = [];
    for (const waiter of waiters) settle(waiter);
  }

  private disposedError(): Error {
    return new Error(`Wire ${this.options.label} follower disposed`);
  }
}

function toError(value: unknown): Error {
  if (value instanceof Error) return value;
  return new Error(String(value));
}
