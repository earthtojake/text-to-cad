import { createEmitter, type SerializedError, type Unsubscribe } from '@emdash/shared';
import type { Logger } from '@emdash/shared/logger';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import type { z } from 'zod';
import type { LiveCursor, LiveSnapshot, LiveUpdate } from '../../api/channel';
import type { WireInstrumentation } from '../../api/instrumentation';
import type { LiveResyncFailurePolicy } from '../follower';
import type { LiveJobState } from '../protocol';
import { LiveStateClient, type LiveChangeMeta } from '../state';

export type LiveJobClientDeps<P, R, E> = {
  refetchSnapshot: () => Promise<LiveSnapshot<LiveJobState<P, R, E>>>;
  /** Required policy deciding what happens when a resync refetch fails. */
  onResyncFailed: LiveResyncFailurePolicy;
  onState?: (state: LiveJobState<P, R, E>) => void;
  instrumentation?: WireInstrumentation;
  logger?: Logger;
  topic?: string;
  clock?: Clock;
};

export class LiveJobFailedError<E> extends Error {
  constructor(
    readonly error: E | undefined,
    options: { cause?: SerializedError } = {}
  ) {
    super('Live job failed');
    this.name = 'LiveJobFailedError';
    this.cause = options.cause;
  }
}

export class LiveJobCancelledError extends Error {
  constructor() {
    super('Live job cancelled');
    this.name = 'LiveJobCancelledError';
  }
}

export class LiveJobClient<P, R, E> {
  readonly result: Promise<R>;

  private readonly progressEmitter = createEmitter<P>();
  private readonly model: LiveStateClient<LiveJobState<P, R, E>>;
  private readonly waiterRejecters = new Set<(error: Error) => void>();
  private lastProgressCount = 0;
  private hasSeeded = false;
  private settled = false;
  private disposed = false;
  private readonly clock: Clock;
  private resolveResult!: (result: R) => void;
  private rejectResult!: (err: unknown) => void;

  constructor(
    stateSchema: z.ZodType<LiveJobState<P, R, E>>,
    private readonly deps: LiveJobClientDeps<P, R, E>
  ) {
    this.clock = deps.clock ?? systemClock;
    this.result = new Promise<R>((resolve, reject) => {
      this.resolveResult = resolve;
      this.rejectResult = reject;
    });
    this.model = new LiveStateClient<LiveJobState<P, R, E>>(
      stateSchema,
      deps.refetchSnapshot,
      (state, meta) => this.handleState(state, meta),
      {
        onResyncFailed: deps.onResyncFailed,
        instrumentation: deps.instrumentation,
        logger: deps.logger,
        topic: deps.topic,
        clock: deps.clock,
      }
    );
  }

  isReady(): boolean {
    return this.model.isReady();
  }

  get cursor(): LiveCursor | undefined {
    return this.model.cursor;
  }

  getState(): LiveJobState<P, R, E> | undefined {
    return this.model.getSnapshot();
  }

  seed(snapshot: LiveSnapshot<LiveJobState<P, R, E>>): void {
    this.model.seed(snapshot);
  }

  applyUpdate(update: LiveUpdate): void {
    this.model.applyUpdate(update);
  }

  /** Resolves only once the follower is fresh; see `LiveFollower.refresh`. */
  refresh(): Promise<void> {
    return this.model.refresh();
  }

  /** Triggers a resync without exposing a promise; failures follow the policy. */
  invalidate(): void {
    this.model.invalidate();
  }

  onProgress(cb: (progress: P) => void): Unsubscribe {
    return this.progressEmitter.subscribe(cb);
  }

  waitForTerminal(timeoutMs = 15_000): Promise<void> {
    if (this.disposed) return Promise.reject(this.disposedError());
    if (this.settled) return Promise.resolve();
    return this.waitForState(
      (state) => state.status !== 'running',
      timeoutMs,
      'Timed out waiting for live job to finish'
    );
  }

  waitForProgressCount(count: number, timeoutMs = 15_000): Promise<void> {
    if (this.disposed) return Promise.reject(this.disposedError());
    if (this.progressCountSatisfies(count)) return Promise.resolve();
    return this.waitForState(
      () => this.progressCountSatisfies(count),
      timeoutMs,
      `Timed out waiting for live job progress count ${count}`
    );
  }

  /** Rejects all pending waiters with a disposed error and stops resyncing. */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    for (const reject of [...this.waiterRejecters]) reject(this.disposedError());
    this.waiterRejecters.clear();
    this.progressEmitter.clear();
    this.stateEmitter.clear();
    this.model.dispose();
  }

  private waitForState(
    satisfied: (state: LiveJobState<P, R, E>) => boolean,
    timeoutMs: number,
    timeoutMessage: string
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const timer =
        timeoutMs > 0
          ? this.clock.schedule(
              timeoutMs,
              () => {
                cleanup();
                reject(new Error(timeoutMessage));
              },
              { unref: true }
            )
          : undefined;
      const unsubscribe = this.onStateChange((state) => {
        if (!satisfied(state)) return;
        cleanup();
        resolve();
      });
      const rejecter = (error: Error): void => {
        cleanup();
        reject(error);
      };
      this.waiterRejecters.add(rejecter);
      const cleanup = (): void => {
        timer?.dispose();
        unsubscribe();
        this.waiterRejecters.delete(rejecter);
      };
    });
  }

  private handleState(state: LiveJobState<P, R, E>, meta: LiveChangeMeta): void {
    this.deps.onState?.(state);
    this.stateEmitter.emit(state);

    if (state.status === 'running') {
      this.emitNewProgress(state, meta);
      return;
    }

    this.settle(state);
  }

  private emitNewProgress(
    state: Extract<LiveJobState<P, R, E>, { status: 'running' }>,
    meta: LiveChangeMeta
  ): void {
    // The first seed restates retained progress the caller never subscribed
    // for; record the count without emitting. Later seeds (resyncs) fall
    // through so progress missed during a gap is caught up — the count-based
    // range below already prevents re-emitting anything seen before.
    if (meta.kind === 'seed' && !this.hasSeeded) {
      this.hasSeeded = true;
      this.lastProgressCount = state.progressCount;
      return;
    }
    if (meta.kind === 'seed') this.hasSeeded = true;

    if (state.progressCount <= this.lastProgressCount) return;

    const retainedStartCount = state.progressCount - state.progress.length;
    const firstNewCount = this.lastProgressCount + 1;
    const firstEmittableCount = Math.max(firstNewCount, retainedStartCount + 1);
    const startIndex = firstEmittableCount - retainedStartCount - 1;

    for (const progress of state.progress.slice(startIndex)) {
      this.progressEmitter.emit(progress);
    }
    this.lastProgressCount = state.progressCount;
  }

  private settle(state: LiveJobState<P, R, E>): void {
    if (this.settled) return;
    this.settled = true;

    if (state.status === 'succeeded') {
      this.resolveResult(state.result);
    } else if (state.status === 'failed') {
      this.rejectResult(new LiveJobFailedError(state.error, { cause: state.cause }));
    } else if (state.status === 'cancelled') {
      this.rejectResult(new LiveJobCancelledError());
    }
  }

  private readonly stateEmitter = createEmitter<LiveJobState<P, R, E>>();

  private onStateChange(cb: (state: LiveJobState<P, R, E>) => void): Unsubscribe {
    return this.stateEmitter.subscribe(cb);
  }

  private progressCountSatisfies(count: number): boolean {
    const state = this.getState();
    return state?.status === 'running' && state.progressCount >= count;
  }

  private disposedError(): Error {
    return new Error('LiveJobClient disposed');
  }
}
