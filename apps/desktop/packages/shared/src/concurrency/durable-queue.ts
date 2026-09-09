import { createConcurrencyLimiter } from './concurrency-limiter';
import type { Scope } from './scope';

export type DurableQueue = {
  poke(): void;
  waitForIdle(): Promise<void>;
  depth(lane: string): number;
};

export type DurableQueueOptions<Row> = {
  scope: Scope;
  list(): Promise<readonly Row[]>;
  laneOf(row: Row): string;
  isRunnable(row: Row): Promise<boolean> | boolean;
  run(row: Row, signal: AbortSignal): Promise<void>;
  maxConcurrentLanes?: number;
  onError(error: unknown): void;
  onPass?(): Promise<void>;
};

export function createDurableQueue<Row>(options: DurableQueueOptions<Row>): DurableQueue {
  const maxConcurrentLanes = options.maxConcurrentLanes ?? 4;
  const limiter = createConcurrencyLimiter(maxConcurrentLanes);
  const activeLanes = new Map<string, Promise<void>>();
  let drainRequested = false;
  let schedulerPromise: Promise<void> | undefined;

  const startLane = (laneKey: string) => {
    if (activeLanes.has(laneKey) || options.scope.disposed) return;
    const run = options.scope.run(`durable-queue:${laneKey}`, async (signal) => {
      await limiter.run(signal, () => runLane(laneKey, signal));
    });
    const promise = run
      .value()
      .catch(options.onError)
      .finally(() => {
        activeLanes.delete(laneKey);
        if (drainRequested) queue.poke();
      });
    activeLanes.set(laneKey, promise);
  };

  const schedule = async (signal: AbortSignal) => {
    if (signal.aborted) return;
    const rows = await options.list();
    const laneKeys = new Set<string>();
    for (const row of rows) laneKeys.add(options.laneOf(row));
    for (const laneKey of laneKeys) {
      if (signal.aborted) return;
      startLane(laneKey);
    }
    await options.onPass?.();
  };

  const runLane = async (laneKey: string, signal: AbortSignal) => {
    let madeProgress = true;
    while (madeProgress && !signal.aborted) {
      madeProgress = false;
      const rows = (await options.list()).filter((row) => options.laneOf(row) === laneKey);
      for (const row of rows) {
        if (signal.aborted) return;
        if (!(await options.isRunnable(row))) continue;
        await options.run(row, signal);
        madeProgress = true;
        await options.onPass?.();
        break;
      }
    }
  };

  const queue: DurableQueue = {
    poke() {
      if (options.scope.disposed) return;
      drainRequested = true;
      if (schedulerPromise) return;
      const run = options.scope.run('durable-queue:schedule', async (signal) => {
        while (drainRequested && !signal.aborted) {
          drainRequested = false;
          await schedule(signal);
        }
      });
      schedulerPromise = run
        .value()
        .catch(options.onError)
        .finally(() => {
          schedulerPromise = undefined;
          if (drainRequested) queue.poke();
        });
    },
    async waitForIdle() {
      for (;;) {
        const promises = [...(schedulerPromise ? [schedulerPromise] : []), ...activeLanes.values()];
        if (promises.length === 0) return;
        await Promise.allSettled(promises);
      }
    },
    depth(lane: string) {
      return activeLanes.has(lane) ? 1 : 0;
    },
  };

  return queue;
}
