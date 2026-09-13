import { log } from '@emdash/shared/logger';
import { createConcurrencyLimiter, type ConcurrencyLimiter } from './concurrency-limiter';

export type KeyedLanes = {
  /** FIFO wait within the lane. */
  run<T>(key: string, signal: AbortSignal, operation: () => Promise<T>): Promise<T>;
  /** Dirty-flag: at most one running + one pending; extra submits fold into the pending run. */
  coalesce(key: string, operation: () => Promise<void>, onError?: (error: unknown) => void): void;
  depth(key: string): number;
};

export type CreateKeyedLanesOptions = {
  limitPerLane?: number;
};

type CoalescedOperation = {
  run(): Promise<void>;
  onError?: (error: unknown) => void;
};

type Lane = {
  limiter: ConcurrencyLimiter;
  runDepth: number;
  coalesceRunning: boolean;
  coalescePending: CoalescedOperation | undefined;
};

export function createKeyedLanes(options: CreateKeyedLanesOptions = {}): KeyedLanes {
  const limitPerLane = options.limitPerLane ?? 1;
  const lanes = new Map<string, Lane>();

  const laneFor = (key: string) => {
    let lane = lanes.get(key);
    if (!lane) {
      lane = {
        limiter: createConcurrencyLimiter(limitPerLane),
        runDepth: 0,
        coalesceRunning: false,
        coalescePending: undefined,
      };
      lanes.set(key, lane);
    }
    return lane;
  };

  const cleanup = (key: string, lane: Lane) => {
    if (
      lane.runDepth === 0 &&
      !lane.coalesceRunning &&
      lane.coalescePending === undefined &&
      lanes.get(key) === lane
    ) {
      lanes.delete(key);
    }
  };

  const drainCoalesced = async (key: string, lane: Lane) => {
    for (;;) {
      const pending = lane.coalescePending;
      if (!pending) break;
      lane.coalescePending = undefined;
      try {
        await pending.run();
      } catch (error) {
        if (pending.onError) pending.onError(error);
        else log.warn('keyed lane coalesce failed', { key, error });
      }
    }
    lane.coalesceRunning = false;
    cleanup(key, lane);
  };

  return {
    async run<T>(key: string, signal: AbortSignal, operation: () => Promise<T>): Promise<T> {
      const lane = laneFor(key);
      lane.runDepth += 1;
      try {
        return await lane.limiter.run(signal, operation);
      } finally {
        lane.runDepth -= 1;
        cleanup(key, lane);
      }
    },
    coalesce(
      key: string,
      operation: () => Promise<void>,
      onError?: (error: unknown) => void
    ): void {
      const lane = laneFor(key);
      lane.coalescePending = { run: operation, onError };
      if (lane.coalesceRunning) return;
      lane.coalesceRunning = true;
      void drainCoalesced(key, lane);
    },
    depth(key: string): number {
      const lane = lanes.get(key);
      if (!lane) return 0;
      return (
        lane.runDepth +
        (lane.coalesceRunning ? 1 : 0) +
        (lane.coalescePending !== undefined ? 1 : 0)
      );
    },
  };
}
