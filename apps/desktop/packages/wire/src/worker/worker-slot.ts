import { createEmitter, type Unsubscribe } from '@emdash/shared';
import { type Run, type Scope } from '@emdash/shared/concurrency';
import type { Logger } from '@emdash/shared/logger';
import { retrySchedule, runWithTimeout, systemClock, type Clock } from '@emdash/shared/scheduling';
import type { ContractClient } from '../api/client';
import { connect, type Connection } from '../api/connect';
import type { Contract, ContractDefinitions } from '../api/define';
import { client as createClient } from '../rpc/client';
import { WorkerLink } from './link';
import { forwardWorkerLogs } from './logging';
import { WORKER_SHUTDOWN_SIGNAL } from './protocol';
import type {
  ProcessExit,
  WireWorker,
  WireWorkerDefinition,
  WireWorkerState,
  WorkerProcess,
  WorkerProcessSpawner,
  WorkerSupervision,
} from './types';

const DEFAULT_READY_TIMEOUT_MS = 10_000;
const DEFAULT_SHUTDOWN_GRACE_MS = 1_000;

export const DEFAULT_WORKER_SUPERVISION: WorkerSupervision = {
  restart: 'on-failure',
  schedule: retrySchedule({ delaysMs: [250, 1_000, 2_500], repeatLast: true, maxRetries: 5 }),
};

export type WorkerSlotOptions<Defs extends ContractDefinitions> = {
  definition: WireWorkerDefinition<Defs>;
  scope: Scope;
  processSpawner: WorkerProcessSpawner;
  clock?: Clock;
  logger: Logger;
  defaultSupervision?: WorkerSupervision;
  defaultReadyTimeoutMs?: number;
  defaultShutdownGraceMs?: number;
};

type CurrentGeneration = {
  generation: number;
  process: WorkerProcess;
  exit: Promise<ProcessExit>;
};

class WorkerExitedBeforeReady extends Error {
  constructor(readonly exit: ProcessExit) {
    super(`Worker exited before ready (code ${exit.code})`);
  }
}

export class WorkerSlot<Defs extends ContractDefinitions> implements WireWorker<Defs> {
  private readonly link = new WorkerLink();
  private readonly stateEmitter = createEmitter<WireWorkerState>();
  private readonly connection: Connection;
  private readonly stableClient: ContractClient<Defs>;
  private readonly clock: Clock;
  private readonly supervision: WorkerSupervision;
  private stateValue: WireWorkerState = { kind: 'idle' };
  private generation = 0;
  private current: CurrentGeneration | undefined;
  private supervisor: Run<void> | undefined;
  private startPromise: Promise<ContractClient<Defs>> | undefined;
  private readonly readyWaiters = new Set<Deferred<ContractClient<Defs>>>();
  private transitionTail: Promise<void> = Promise.resolve();
  private disposed = false;

  constructor(private readonly options: WorkerSlotOptions<Defs>) {
    this.clock = options.clock ?? systemClock;
    this.supervision =
      options.definition.supervision ?? options.defaultSupervision ?? DEFAULT_WORKER_SUPERVISION;
    this.connection = connect(this.link, {
      instrumentation: options.definition.instrumentation,
      clock: this.clock,
    });
    this.stableClient = createClient(options.definition.contract, this.connection);
    options.scope.add(() => this.dispose());
  }

  get name(): string {
    return this.options.definition.name;
  }

  get contract(): Contract<Defs> {
    return this.options.definition.contract;
  }

  get state(): WireWorkerState {
    return this.stateValue;
  }

  ready(): Promise<ContractClient<Defs>> {
    if (this.stateValue.kind === 'ready') return Promise.resolve(this.stableClient);
    if (this.disposed || this.options.scope.disposed) {
      return Promise.reject(new Error(`Wire worker '${this.name}' is disposed`));
    }
    if (!this.startPromise) {
      const waiter = createDeferred<ContractClient<Defs>>();
      this.readyWaiters.add(waiter);
      this.startPromise = waiter.promise.finally(() => {
        this.readyWaiters.delete(waiter);
        this.startPromise = undefined;
      });
      void this.transition(async () => {
        if (!this.supervisor || this.supervisor.signal.aborted) {
          this.supervisor = this.options.scope.run(
            'supervise',
            async (signal) => {
              try {
                await this.supervise(signal);
              } finally {
                this.supervisor = undefined;
              }
            },
            { onFailure: 'report' }
          );
        }
      });
    }
    return this.startPromise;
  }

  async stop(): Promise<void> {
    await this.transition(async () => {
      if (this.disposed || this.stateValue.kind === 'idle' || this.stateValue.kind === 'disposed') {
        return;
      }
      this.setState({ kind: 'stopping' });
      this.supervisor?.cancel(new Error(`Wire worker '${this.name}' stopped`));
      this.supervisor = undefined;
      await this.stopCurrentGeneration();
      this.rejectReadyWaiters(new Error(`Wire worker '${this.name}' stopped`));
      this.setState({ kind: 'idle' });
    });
  }

  async restart(_reason?: unknown): Promise<void> {
    await this.stop();
    await this.ready();
  }

  onStateChanged(cb: (state: WireWorkerState) => void): Unsubscribe {
    return this.stateEmitter.subscribe(cb);
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    await this.stop();
    this.disposed = true;
    this.link.close();
    this.setState({ kind: 'disposed' });
  }

  private async supervise(signal: AbortSignal): Promise<void> {
    let attempt = 0;
    for (;;) {
      if (signal.aborted || this.disposed) return;
      const generation = ++this.generation;
      try {
        const exit = await this.runGeneration(generation, attempt, signal);
        if (signal.aborted || this.disposed) return;
        const delay = this.retryDelay(exit, attempt);
        if (delay === undefined) {
          this.setState({ kind: 'failed', attempts: attempt + 1, lastExit: exit });
          this.rejectReadyWaiters(new WorkerExitedBeforeReady(exit));
          return;
        }
        this.setState({ kind: 'restarting', generation, attempt, lastExit: exit });
        await this.clock.sleep(delay, { signal, unref: true });
        attempt += 1;
      } catch (error) {
        if (signal.aborted || this.disposed) return;
        if (error instanceof WorkerExitedBeforeReady) {
          const delay = this.retryDelay(error.exit, attempt);
          if (delay === undefined) {
            this.setState({ kind: 'failed', attempts: attempt + 1, lastExit: error.exit });
            this.rejectReadyWaiters(error);
            return;
          }
          this.setState({ kind: 'restarting', generation, attempt, lastExit: error.exit });
          await this.clock.sleep(delay, { signal, unref: true });
          attempt += 1;
          continue;
        }
        this.setState({ kind: 'failed', attempts: attempt + 1, error });
        this.rejectReadyWaiters(error);
        return;
      }
    }
  }

  private async runGeneration(
    generation: number,
    attempt: number,
    signal: AbortSignal
  ): Promise<ProcessExit> {
    const generationScope = this.options.scope.child(`generation:${generation}`);
    let process: WorkerProcess | undefined;
    this.setState({ kind: 'starting', generation, attempt });
    try {
      process = await this.options.processSpawner.spawn(
        this.options.definition.process(),
        generationScope
      );
      const exit = this.waitForExit(generation, process);
      this.current = { generation, process, exit };
      this.link.attach(generation, process);
      generationScope.add(
        process.onMessage((message) => this.link.handleMessage(generation, message))
      );
      generationScope.add(
        forwardWorkerLogs(process, this.options.logger, { source: `${this.name}-runtime` })
      );
      await this.options.definition.setup?.({ generation, process, scope: generationScope });

      await Promise.race([
        this.waitForReady(generation, signal),
        exit.then((value) => {
          throw new WorkerExitedBeforeReady(value);
        }),
      ]);

      this.link.markReady(generation);
      this.setState({ kind: 'ready', generation, attempt, pid: process.pid });
      this.resolveReadyWaiters();

      const terminalExit = await Promise.race([
        exit,
        waitForAbort(signal).then((reason) => {
          throw reason;
        }),
      ]);
      this.link.detach(generation, terminalExit);
      return terminalExit;
    } finally {
      if (signal.aborted && process) await this.stopProcess(process, generation);
      if (this.current?.generation === generation) this.current = undefined;
      await generationScope.dispose();
    }
  }

  private waitForReady(generation: number, signal: AbortSignal): Promise<void> {
    if (this.link.hasReadySignal(generation)) return Promise.resolve();
    return runWithTimeout(
      (timeoutSignal) =>
        new Promise<void>((resolve, reject) => {
          const unsubscribe = this.link.onReady((readyGeneration) => {
            if (readyGeneration !== generation) return;
            cleanup();
            resolve();
          });
          const onAbort = (): void => {
            cleanup();
            reject(timeoutSignal.reason ?? new Error('Worker readiness cancelled'));
          };
          timeoutSignal.addEventListener('abort', onAbort, { once: true });
          function cleanup(): void {
            unsubscribe();
            timeoutSignal.removeEventListener('abort', onAbort);
          }
        }),
      {
        timeoutMs:
          this.options.definition.readyTimeoutMs ??
          this.options.defaultReadyTimeoutMs ??
          DEFAULT_READY_TIMEOUT_MS,
        clock: this.clock,
        signal,
      }
    );
  }

  private waitForExit(generation: number, process: WorkerProcess): Promise<ProcessExit> {
    return new Promise((resolve) => {
      const unsubscribe = process.onExit((exit) => {
        unsubscribe();
        const level = this.shouldRestart(exit, this.retryAttempt())
          ? 'warn'
          : exit.code
            ? 'error'
            : 'info';
        this.options.logger[level]('worker process exited', {
          worker: this.name,
          generation,
          ...exit,
        });
        resolve(exit);
      });
    });
  }

  private async stopCurrentGeneration(): Promise<void> {
    const current = this.current;
    if (!current) return;
    const process = current.process;
    const exit = current.exit.catch(() => undefined);
    await this.stopProcess(process, current.generation, exit);
  }

  private async stopProcess(
    process: WorkerProcess,
    generation: number,
    exit: Promise<ProcessExit | undefined> = this.current?.exit.catch(() => undefined) ??
      Promise.resolve(undefined)
  ): Promise<void> {
    try {
      process.send(WORKER_SHUTDOWN_SIGNAL);
    } catch {}

    await Promise.race([
      exit,
      this.clock
        .sleep(this.shutdownGraceMs(), {
          unref: true,
        })
        .catch(() => undefined),
    ]);

    if (this.current?.generation === generation) await process.kill();
    this.link.detach(generation);
  }

  private retryAttempt(): number {
    const state = this.stateValue;
    return 'attempt' in state ? state.attempt : 0;
  }

  private retryDelay(exit: ProcessExit, attempt: number): number | undefined {
    if (!this.shouldRestart(exit, attempt)) return undefined;
    if (this.supervision.restart !== 'on-failure') return undefined;
    return this.supervision.schedule.delayFor(attempt);
  }

  private shouldRestart(exit: ProcessExit, attempt: number): boolean {
    if (this.supervision.restart !== 'on-failure') return false;
    if (exit.code === 0 && exit.signal == null) return false;
    return this.supervision.schedule.delayFor(attempt) !== undefined;
  }

  private shutdownGraceMs(): number {
    return (
      this.options.definition.shutdownGraceMs ??
      this.options.defaultShutdownGraceMs ??
      DEFAULT_SHUTDOWN_GRACE_MS
    );
  }

  private setState(state: WireWorkerState): void {
    this.stateValue = state;
    this.stateEmitter.emit(state);
  }

  private resolveReadyWaiters(): void {
    for (const waiter of [...this.readyWaiters]) {
      waiter.resolve(this.stableClient);
    }
    this.readyWaiters.clear();
  }

  private rejectReadyWaiters(error: unknown): void {
    for (const waiter of [...this.readyWaiters]) {
      waiter.reject(error);
    }
    this.readyWaiters.clear();
  }

  private transition<T>(operation: () => Promise<T>): Promise<T> {
    const next = this.transitionTail.then(operation, operation);
    this.transitionTail = next.then(
      () => undefined,
      () => undefined
    );
    return next;
  }
}

function waitForAbort(signal: AbortSignal): Promise<unknown> {
  if (signal.aborted) return Promise.resolve(signal.reason);
  return new Promise((resolve) => {
    signal.addEventListener('abort', () => resolve(signal.reason), { once: true });
  });
}

type Deferred<T> = {
  readonly promise: Promise<T>;
  readonly settled: boolean;
  resolve(value: T): void;
  reject(error: unknown): void;
};

function createDeferred<T>(): Deferred<T> {
  let resolve: (value: T) => void = () => {};
  let reject: (error: unknown) => void = () => {};
  let settled = false;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = (value) => {
      if (settled) return;
      settled = true;
      promiseResolve(value);
    };
    reject = (error) => {
      if (settled) return;
      settled = true;
      promiseReject(error);
    };
  });
  return {
    promise,
    get settled() {
      return settled;
    },
    resolve,
    reject,
  };
}
