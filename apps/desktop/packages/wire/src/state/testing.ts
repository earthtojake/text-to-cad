import { createScope, type Scope } from '@emdash/shared/concurrency';
import { observe, flushStateTurn, type Readable, type Snapshot } from './core';
import type { QueryLane } from './query';

export type RecordedSnapshots<T> = {
  readonly snapshots: Snapshot<T>[];
  readonly scope: Scope;
  dispose(): Promise<void>;
};

export function recordSnapshots<T>(
  node: Readable<T>,
  options: { immediate?: boolean } = {}
): RecordedSnapshots<T> {
  const scope = createScope();
  const snapshots: Snapshot<T>[] = [];
  observe(node, (current) => snapshots.push(current), {
    scope,
    immediate: options.immediate,
  });
  return {
    snapshots,
    scope,
    dispose: () => scope.dispose(),
  };
}

export async function settleAsync(turns = 4): Promise<void> {
  for (let index = 0; index < turns; index += 1) {
    await Promise.resolve();
    flushStateTurn();
  }
}

export function createRecordingLane(): QueryLane & { readonly runs: number[] } {
  const runs: number[] = [];
  return {
    runs,
    async run<T>(work: () => Promise<T> | T): Promise<T> {
      runs.push(runs.length + 1);
      return await work();
    },
  };
}
