import { log as ambientLog, type Logger } from '@emdash/shared/logger';
import { systemClock, type Clock } from '../scheduling';
import type { Disposable } from './disposable';

export type ScopeCleanup = () => void | Promise<void>;
export type ScopeState = 'open' | 'closing' | 'closed';

export type RunExit<A> =
  | {
      kind: 'success';
      value: A;
    }
  | {
      kind: 'failure';
      error: unknown;
    }
  | {
      kind: 'cancelled';
      reason: unknown;
    };

export type RunDescription = {
  label: string;
  startedAt: number;
  cancelled: boolean;
};

export interface Run<A> {
  readonly label: string;
  readonly startedAt: number;
  readonly signal: AbortSignal;
  readonly exit: Promise<RunExit<A>>;
  cancel(reason?: unknown): void;
  value(): Promise<A>;
}

export type ScopeCleanupErrorContext = {
  label: string | undefined;
  labelPath: string | undefined;
  logger: Logger;
};

export interface Scope {
  readonly state: ScopeState;
  readonly disposed: boolean;
  readonly signal: AbortSignal;
  readonly log: Logger;
  add(cleanup: ScopeCleanup): void;
  use<T extends Disposable>(resource: T): T;
  child(label?: string): Scope;
  run<A>(
    label: string,
    operation: (signal: AbortSignal) => A | Promise<A>,
    options?: { onFailure?: 'report' | 'close-scope' }
  ): Run<A>;
  dispose(reason?: unknown): Promise<void>;
}

export type CreateScopeOptions = {
  label?: string;
  logger?: Logger;
  clock?: Clock;
  onCleanupError?: (error: unknown, scope: ScopeCleanupErrorContext) => void;
};

export type ScopeDescription = {
  label: string | undefined;
  labelPath: string | undefined;
  state: ScopeState;
  disposed: boolean;
  runs: RunDescription[];
  children: ScopeDescription[];
};

type ScopeData = {
  label: string | undefined;
  labelPath: string | undefined;
  logger: Logger;
  cleanups: ScopeCleanup[];
  children: Set<ScopeImpl>;
  runs: Set<RunImpl<unknown>>;
  onCleanupError: (error: unknown, scope: ScopeCleanupErrorContext) => void;
  clock: Clock;
  controller: AbortController;
  state: ScopeState;
  disposePromise: Promise<void> | undefined;
};

export function createScope(options: CreateScopeOptions = {}): Scope {
  const logger = createScopeLogger(options.logger ?? ambientLog, options.label);
  return new ScopeImpl({
    label: options.label,
    labelPath: options.label,
    logger,
    cleanups: [],
    children: new Set(),
    runs: new Set(),
    onCleanupError: options.onCleanupError ?? defaultCleanupErrorHandler,
    clock: options.clock ?? systemClock,
    controller: new AbortController(),
    state: 'open',
    disposePromise: undefined,
  });
}

class ScopeImpl implements Scope {
  constructor(readonly data: ScopeData) {}

  get state(): ScopeState {
    return this.data.state;
  }

  get disposed(): boolean {
    return this.data.state !== 'open';
  }

  get signal(): AbortSignal {
    return this.data.controller.signal;
  }

  get log(): Logger {
    return this.data.logger;
  }

  add(cleanup: ScopeCleanup): void {
    if (this.data.state === 'closed') {
      void this.runCleanup(cleanup);
      return;
    }
    this.data.cleanups.push(cleanup);
  }

  use<T extends Disposable>(resource: T): T {
    this.add(() => resource.dispose());
    return resource;
  }

  child(label?: string): Scope {
    const labelPath = joinScopePath(this.data.labelPath, label);
    const child = new ScopeImpl({
      label,
      labelPath,
      cleanups: [],
      children: new Set(),
      runs: new Set(),
      onCleanupError: this.data.onCleanupError,
      clock: this.data.clock,
      logger: createScopeLogger(this.data.logger, labelPath),
      controller: new AbortController(),
      state: 'open',
      disposePromise: undefined,
    });

    if (this.data.state !== 'open') {
      void child.dispose();
      return child;
    }

    this.data.children.add(child);
    child.add(() => {
      this.data.children.delete(child);
    });
    return child;
  }

  run<A>(
    label: string,
    operation: (signal: AbortSignal) => A | Promise<A>,
    options: { onFailure?: 'report' | 'close-scope' } = {}
  ): Run<A> {
    if (this.data.state !== 'open') {
      return cancelledRun(
        label,
        this.data.clock.now(),
        this.abortReason() ?? new Error('Scope is closed')
      );
    }

    const run = new RunImpl<A>(
      label,
      this.data.clock.now(),
      this.data.logger,
      options.onFailure ?? 'report'
    );
    this.data.runs.add(run as RunImpl<unknown>);
    run.start(operation, (exit) => {
      this.data.runs.delete(run as RunImpl<unknown>);
      if (exit.kind === 'failure' && options.onFailure === 'close-scope') {
        void this.dispose(exit.error);
      }
    });
    return run;
  }

  dispose(reason?: unknown): Promise<void> {
    if (this.data.disposePromise) return this.data.disposePromise;
    this.data.state = 'closing';
    this.abort(reason ?? new Error('Scope disposed'));
    this.data.disposePromise = this.disposeAll().finally(() => {
      this.data.state = 'closed';
    });
    return this.data.disposePromise;
  }

  private async disposeAll(): Promise<void> {
    const children = [...this.data.children].reverse();
    this.data.children.clear();
    const runs = [...this.data.runs];

    for (const run of runs) {
      run.cancel(this.abortReason());
    }

    const childDisposals = children.map((child) => child.dispose(this.abortReason()));
    await Promise.all(childDisposals);
    await Promise.all(runs.map((run) => run.exit));

    while (this.data.cleanups.length > 0) {
      const cleanup = this.data.cleanups.pop();
      if (!cleanup) continue;
      await this.runCleanup(cleanup);
    }
  }

  private abort(reason: unknown): void {
    if (!this.data.controller.signal.aborted) this.data.controller.abort(reason);
  }

  private abortReason(): unknown {
    return this.data.controller.signal.reason;
  }

  private async runCleanup(cleanup: ScopeCleanup): Promise<void> {
    try {
      await cleanup();
    } catch (error) {
      this.data.onCleanupError(error, {
        label: this.data.label,
        labelPath: this.data.labelPath,
        logger: this.data.logger,
      });
    }
  }
}

class RunImpl<A> implements Run<A> {
  readonly controller = new AbortController();
  private readonly exitPromise: Promise<RunExit<A>>;
  private resolveExit!: (exit: RunExit<A>) => void;

  constructor(
    readonly label: string,
    readonly startedAt: number,
    private readonly logger: Logger,
    private readonly onFailure: 'report' | 'close-scope'
  ) {
    this.exitPromise = new Promise<RunExit<A>>((resolve) => {
      this.resolveExit = resolve;
    });
  }

  get signal(): AbortSignal {
    return this.controller.signal;
  }

  get exit(): Promise<RunExit<A>> {
    return this.exitPromise;
  }

  start(
    operation: (signal: AbortSignal) => A | Promise<A>,
    onSettled: (exit: RunExit<A>) => void
  ): void {
    void (async () => {
      let exit: RunExit<A>;
      try {
        await Promise.resolve();
        if (this.signal.aborted) throw cancellationError(this.cancelReason());
        const value = await operation(this.signal);
        exit = this.signal.aborted
          ? { kind: 'cancelled', reason: this.cancelReason() }
          : { kind: 'success', value };
      } catch (error) {
        exit = this.signal.aborted
          ? { kind: 'cancelled', reason: this.cancelReason() }
          : { kind: 'failure', error };
      }

      if (exit.kind === 'failure') this.reportFailure(exit.error);
      onSettled(exit);
      this.resolveExit(exit);
    })();
  }

  cancel(reason: unknown = new Error('Run cancelled')): void {
    if (!this.signal.aborted) this.controller.abort(reason);
  }

  async value(): Promise<A> {
    const exit = await this.exit;
    switch (exit.kind) {
      case 'success':
        return exit.value;
      case 'failure':
        throw exit.error;
      case 'cancelled':
        throw cancellationError(exit.reason);
    }
  }

  private cancelReason(): unknown {
    return this.signal.reason;
  }

  private reportFailure(error: unknown): void {
    this.logger.warn('scope run failed', {
      label: this.label,
      error,
      closeScope: this.onFailure === 'close-scope',
    });
  }
}

function cancelledRun<A>(label: string, startedAt: number, reason: unknown): Run<A> {
  const controller = new AbortController();
  controller.abort(reason);
  const exit: Promise<RunExit<A>> = Promise.resolve({ kind: 'cancelled', reason });
  return {
    label,
    startedAt,
    signal: controller.signal,
    exit,
    cancel() {},
    async value(): Promise<A> {
      throw cancellationError(reason);
    },
  };
}

function defaultCleanupErrorHandler(error: unknown, scope: ScopeCleanupErrorContext): void {
  scope.logger.warn('scope cleanup failed', {
    label: scope.label,
    labelPath: scope.labelPath,
    error,
  });
}

export function describeScope(scope: Scope): ScopeDescription {
  if (!(scope instanceof ScopeImpl)) {
    return {
      label: undefined,
      labelPath: undefined,
      state: scope.state,
      disposed: scope.disposed,
      runs: [],
      children: [],
    };
  }
  return describeScopeImpl(scope);
}

function describeScopeImpl(scope: ScopeImpl): ScopeDescription {
  return {
    label: scope.data.label,
    labelPath: scope.data.labelPath,
    state: scope.data.state,
    disposed: scope.disposed,
    runs: [...scope.data.runs].map((run) => ({
      label: run.label,
      startedAt: run.startedAt,
      cancelled: run.signal.aborted,
    })),
    children: [...scope.data.children].map((child) => describeScopeImpl(child)),
  };
}

function createScopeLogger(logger: Logger, labelPath: string | undefined): Logger {
  return labelPath ? logger.child({ scope: labelPath }) : logger;
}

function joinScopePath(parent: string | undefined, label: string | undefined): string | undefined {
  if (!label) return parent;
  return parent ? `${parent}/${label}` : label;
}

function cancellationError(reason: unknown): unknown {
  return reason instanceof Error ? reason : new Error(String(reason ?? 'Run cancelled'));
}
