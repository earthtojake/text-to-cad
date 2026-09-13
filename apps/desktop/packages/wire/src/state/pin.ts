import { createScope, type Scope } from '@emdash/shared/concurrency';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import { observe, snapshot, weakerStatus, type Readable, type StateStatus } from './core';

export type PinSet = {
  readonly status: StateStatus;
  settled(): Promise<void>;
};

export function pin(scope: Scope, nodes: readonly Readable<unknown>[]): PinSet {
  let status: StateStatus = 'live';
  let resolveSettled: (() => void) | undefined;
  let settledPromise: Promise<void> | undefined;

  const recompute = () => {
    status = nodes.reduce<StateStatus>(
      (current, node) => weakerStatus(current, snapshot(node).status),
      'live'
    );
    if (status !== 'loading') {
      resolveSettled?.();
      resolveSettled = undefined;
      settledPromise = undefined;
    }
  };

  for (const node of nodes) {
    observe(node, recompute, { scope, immediate: false });
  }
  recompute();

  return {
    get status() {
      return status;
    },
    settled() {
      if (status !== 'loading') return Promise.resolve();
      settledPromise ??= new Promise<void>((resolve) => {
        resolveSettled = resolve;
      });
      return settledPromise;
    },
  };
}

export function prefetch(
  node: Readable<unknown>,
  options: { ttlMs: number; clock?: Clock; scope?: Scope }
): void {
  const clock = options.clock ?? systemClock;
  const scope = options.scope?.child('prefetch') ?? createScope({ label: 'prefetch', clock });
  pin(scope, [node]);
  clock.schedule(options.ttlMs, () => void scope.dispose(), { unref: true });
}
