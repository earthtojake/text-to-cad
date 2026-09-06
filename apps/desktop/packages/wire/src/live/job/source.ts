import { toSerializedError, type Result } from '@emdash/shared';
import { createScope, type Run, type Scope } from '@emdash/shared/concurrency';
import { systemClock, type Clock, type TimerHandle } from '@emdash/shared/scheduling';
import type { LiveSnapshot, LiveSource } from '../../api/channel';
import type { LiveJobState } from '../protocol';
import { LiveStateSource } from '../state';

const LIVE_JOB_MAX_PROGRESS_ENTRIES = 100;
export const LIVE_JOB_TERMINAL_RETAIN_MS = 5 * 60 * 1000;

export type LiveJobContext<P> = {
  jobId: string;
  signal: AbortSignal;
  progress: (progress: P) => void;
};

export type LiveJobHandler<I, P, R, E> = (
  input: I,
  ctx: LiveJobContext<P>
) => Promise<Result<R, E>> | Result<R, E>;

export type LiveJobListEntry = {
  jobId: string;
  status: LiveJobState<unknown, unknown, unknown>['status'];
  startedAt: number;
  finishedAt?: number;
};

export type LiveJobSourceOptions<E = unknown> = {
  scope?: Scope;
  generation?: number;
  terminalRetainMs?: number;
  idFactory?: () => string;
  clock?: Clock | (() => number);
  toError?: (err: unknown) => E;
  onRunStarted?: (entry: LiveJobListEntry) => void;
  onRunChanged?: (entry: LiveJobListEntry) => void;
  onRunEvicted?: (jobId: string) => void;
};

type LiveJobRun<P, R, E> = {
  scope: Scope;
  execution: Run<void>;
  model: LiveStateSource<LiveJobState<P, R, E>>;
  evictionTimer: TimerHandle | undefined;
};

/**
 * Transport-agnostic cancellable job source.
 *
 * Each run is represented by a LiveStateSource-backed state resource, so jobs inherit
 * the snapshot/update protocol used by LiveStateSource while keeping execution,
 * cancellation, and terminal retention scoped to this primitive.
 *
 * A LiveJobSource survives transport disconnects, but it is process-local and not
 * durable across host process restarts. Terminal runs are retained only until
 * the configured eviction delay expires.
 */
export class LiveJobSource<I, P, R, E> {
  private readonly scope: Scope;
  private readonly runs = new Map<string, LiveJobRun<P, R, E>>();
  private readonly generation: number | undefined;
  private readonly terminalRetainMs: number;
  private readonly idFactory: () => string;
  private readonly clock: Clock;
  private disposePromise: Promise<void> | undefined;

  constructor(
    private readonly handler: LiveJobHandler<I, P, R, E>,
    private readonly options: LiveJobSourceOptions<E> = {}
  ) {
    this.scope = options.scope
      ? options.scope.child('live-job')
      : createScope({ label: 'live-job' });
    this.generation = options.generation;
    this.terminalRetainMs = Math.max(0, options.terminalRetainMs ?? LIVE_JOB_TERMINAL_RETAIN_MS);
    this.idFactory = options.idFactory ?? (() => crypto.randomUUID());
    this.clock = normalizeClock(options.clock);
    this.scope.add(() => {
      this.runs.clear();
    });
  }

  start(input: I): { jobId: string } {
    if (this.scope.disposed) throw new Error('LiveJobSource is disposed');
    const jobId = this.idFactory();
    const jobScope = this.scope.child(`job:${jobId}`);
    const now = this.clock.now();
    const model = new LiveStateSource<LiveJobState<P, R, E>>(
      {
        status: 'running',
        startedAt: now,
        progress: [],
        progressCount: 0,
      },
      this.generation ?? now
    );
    const run: LiveJobRun<P, R, E> = {
      scope: jobScope,
      execution: undefined as unknown as Run<void>,
      model,
      evictionTimer: undefined,
    };
    run.execution = jobScope.run('execute', (signal) => this.execute(jobId, input, run, signal));

    this.runs.set(jobId, run);
    this.options.onRunStarted?.(this.toListEntry(jobId, run));

    return { jobId };
  }

  cancel(jobId: string): void {
    const run = this.runs.get(jobId);
    if (!run || run.execution.signal.aborted || !this.isRunning(run)) return;
    run.execution.cancel(new Error(`Live job '${jobId}' cancelled`));
  }

  source(jobId: string): LiveSource | undefined {
    return this.runs.get(jobId)?.model;
  }

  snapshot(jobId: string): LiveSnapshot<LiveJobState<P, R, E>> | undefined {
    return this.runs.get(jobId)?.model.snapshot();
  }

  getState(jobId: string): LiveJobState<P, R, E> | undefined {
    return this.snapshot(jobId)?.data;
  }

  private liveJob(jobId: string): LiveStateSource<LiveJobState<P, R, E>> | undefined {
    return this.runs.get(jobId)?.model;
  }

  dispose(): Promise<void> {
    if (this.disposePromise) return this.disposePromise;
    this.disposePromise = this.scope.dispose(new Error('LiveJobSource disposed'));
    return this.disposePromise;
  }

  private async execute(
    jobId: string,
    input: I,
    run: LiveJobRun<P, R, E>,
    signal: AbortSignal
  ): Promise<void> {
    try {
      const result = await this.handler(input, {
        jobId,
        signal,
        progress: (progress) => this.reportProgress(run, progress),
      });
      if (signal.aborted) this.markCancelled(run);
      else if (result.success) this.markSucceeded(run, result.data);
      else this.markFailed(run, result.error, false);
    } catch (err) {
      if (signal.aborted) {
        this.markCancelled(run);
      } else {
        this.markFailed(run, err, true);
      }
    } finally {
      if (this.scope.state === 'open' && run.scope.state === 'open') {
        this.scheduleEviction(jobId, run);
      }
    }
  }

  private reportProgress(run: LiveJobRun<P, R, E>, progress: P): void {
    if (run.execution.signal.aborted) return;
    run.model.produce((draft) => {
      if (draft.status !== 'running') return;
      draft.progress.push(progress);
      if (draft.progress.length > LIVE_JOB_MAX_PROGRESS_ENTRIES) {
        draft.progress.splice(0, draft.progress.length - LIVE_JOB_MAX_PROGRESS_ENTRIES);
      }
      draft.progressCount += 1;
    });
  }

  private markSucceeded(run: LiveJobRun<P, R, E>, result: R): void {
    run.model.produce((draft) => {
      if (draft.status !== 'running') return;
      return {
        status: 'succeeded',
        startedAt: draft.startedAt,
        finishedAt: this.clock.now(),
        progress: [...draft.progress],
        result,
      };
    });
  }

  private markFailed(run: LiveJobRun<P, R, E>, err: unknown, thrown: boolean): void {
    const mapped = thrown && this.options.toError ? this.options.toError(err) : undefined;
    run.model.produce((draft) => {
      if (draft.status !== 'running') return;
      const failed: LiveJobState<P, R, E> = {
        status: 'failed',
        startedAt: draft.startedAt,
        finishedAt: this.clock.now(),
        progress: [...draft.progress],
      };
      if (thrown && mapped === undefined) failed.cause = toSerializedError(err);
      else failed.error = (thrown ? mapped : err) as E;
      return failed;
    });
  }

  private markCancelled(run: LiveJobRun<P, R, E>): void {
    run.model.produce((draft) => {
      if (draft.status !== 'running') return;
      return {
        status: 'cancelled',
        startedAt: draft.startedAt,
        finishedAt: this.clock.now(),
        progress: [...draft.progress],
      };
    });
  }

  private scheduleEviction(jobId: string, run: LiveJobRun<P, R, E>): void {
    if (this.runs.get(jobId) !== run) return;
    this.options.onRunChanged?.(this.toListEntry(jobId, run));
    run.evictionTimer?.dispose();
    run.evictionTimer = this.clock.schedule(
      this.terminalRetainMs,
      () => {
        if (this.runs.get(jobId) !== run) return;
        this.runs.delete(jobId);
        this.options.onRunEvicted?.(jobId);
        void run.scope.dispose(new Error(`Live job '${jobId}' evicted`));
      },
      { unref: true }
    );
    run.scope.add(() => {
      run.evictionTimer?.dispose();
      run.evictionTimer = undefined;
    });
  }

  private isRunning(run: LiveJobRun<P, R, E>): boolean {
    return run.model.snapshot().data.status === 'running';
  }

  private toListEntry(jobId: string, run: LiveJobRun<P, R, E>): LiveJobListEntry {
    const state = run.model.snapshot().data;
    return {
      jobId,
      status: state.status,
      startedAt: state.startedAt,
      finishedAt: state.status === 'running' ? undefined : state.finishedAt,
    };
  }
}

function normalizeClock(clock: Clock | (() => number) | undefined): Clock {
  if (!clock) return systemClock;
  if (typeof clock === 'function') {
    return {
      ...systemClock,
      now: clock,
    };
  }
  return clock;
}
