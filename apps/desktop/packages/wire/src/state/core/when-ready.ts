import type { Scope } from '@emdash/shared/concurrency';
import type { Readable, Snapshot } from './node';
import { observe } from './observe';

export function whenReady<T>(node: Readable<T>, options: { scope: Scope }): Promise<Snapshot<T>> {
  const initial = currentSnapshot(node);
  if (options.scope.disposed && initial) return Promise.resolve(initial);

  let latest = initial;
  if (latest && latest.status !== 'loading') return Promise.resolve(latest);

  let settled = false;
  return new Promise<Snapshot<T>>((resolve) => {
    const settle = (next: Snapshot<T>): void => {
      if (settled) return;
      settled = true;
      resolve(next);
    };

    observe(
      node,
      (next) => {
        latest = next;
        if (next.status !== 'loading') settle(next);
      },
      { scope: options.scope }
    );
    options.scope.add(() => settle(latest ?? loadingSnapshot<T>()));
  });
}

function currentSnapshot<T>(node: Readable<T>): Snapshot<T> | undefined {
  const state = node.__stateNode as unknown as {
    currentSnapshot?: () => Snapshot<T>;
  };
  return state.currentSnapshot?.();
}

function loadingSnapshot<T>(): Snapshot<T> {
  return {
    value: undefined as T,
    status: 'loading',
    revision: 0,
  };
}
