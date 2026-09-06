import { err, ok } from '@emdash/shared';
import { createManualClock } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { cell, flushStateTurn, snapshot } from './core';
import { optimistic } from './optimistic';
import { recordSnapshots, settleAsync } from './testing';

describe('optimistic state', () => {
  it('composes overlapping patches in submission order', async () => {
    const base = cell({ count: 1, label: 'a' });
    const view = optimistic(base);
    const recorded = recordSnapshots(view);

    view.apply(
      (draft) => {
        draft.count += 1;
        draft.label += 'b';
      },
      { mutationId: 'm1' }
    );
    view.apply(
      (draft) => {
        draft.count *= 10;
        draft.label += 'c';
      },
      { mutationId: 'm2' }
    );
    flushStateTurn();

    expect(snapshot(view).value).toEqual({ count: 20, label: 'abc' });
    expect(recorded.snapshots.map((current) => current.value)).toEqual([
      { count: 1, label: 'a' },
      { count: 20, label: 'abc' },
    ]);
    await recorded.dispose();
  });

  it('rolls back an unapplied patch when its ttl expires', async () => {
    const clock = createManualClock();
    const base = cell({ count: 1 });
    const view = optimistic(base, { clock, ttlMs: 10 });
    const recorded = recordSnapshots(view);

    view.apply(
      (draft) => {
        draft.count += 1;
      },
      { mutationId: 'm1' }
    );
    flushStateTurn();
    await clock.advanceBy(10);
    flushStateTurn();

    expect(recorded.snapshots.map((current) => current.value?.count)).toEqual([1, 2, 1]);
    await recorded.dispose();
  });

  it('drops a patch when the mutation returns an error', async () => {
    const base = cell({ count: 1 });
    const view = optimistic(base);
    const recorded = recordSnapshots(view);

    const result = await view.run(
      async () => ({
        result: err('nope'),
        settled: Promise.resolve(),
      }),
      undefined,
      (draft) => {
        draft.count += 1;
      }
    );
    flushStateTurn();

    expect(result).toEqual(err('nope'));
    expect(recorded.snapshots.map((current) => current.value?.count)).toEqual([1, 2, 1]);
    await recorded.dispose();
  });

  it('drops a patch when the mutation throws', async () => {
    const base = cell({ count: 1 });
    const view = optimistic(base);
    const recorded = recordSnapshots(view);

    await expect(
      view.run(
        async () => {
          throw new Error('boom');
        },
        undefined,
        (draft) => {
          draft.count += 1;
        }
      )
    ).rejects.toThrow('boom');
    flushStateTurn();

    expect(recorded.snapshots.map((current) => current.value?.count)).toEqual([1, 2, 1]);
    await recorded.dispose();
  });

  it('keeps a patch visible until the successful mutation has settled', async () => {
    const base = cell({ count: 1 });
    const view = optimistic(base);
    const settled = deferred<void>();
    const recorded = recordSnapshots(view);

    const result = view.run(
      async (_input, { mutationId }) => {
        base.set({ count: 2 }, { mutationIds: [mutationId] });
        return {
          result: ok('done'),
          settled: settled.promise,
        };
      },
      undefined,
      (draft) => {
        draft.count += 1;
      }
    );
    await settleAsync();
    expect(snapshot(view).value?.count).toBe(2);

    settled.resolve(undefined);
    await result;
    flushStateTurn();

    expect(recorded.snapshots.map((current) => current.value?.count)).toEqual([1, 2, 2]);
    await recorded.dispose();
  });

  it('hides pending patches after a base generation change', async () => {
    const base = cell({ count: 1 });
    const view = optimistic(base);
    const recorded = recordSnapshots(view);

    view.apply(
      (draft) => {
        draft.count += 1;
      },
      { mutationId: 'm1' }
    );
    flushStateTurn();
    base.set({ count: 1 }, { generation: 2 });
    flushStateTurn();

    expect(recorded.snapshots.map((current) => current.value?.count)).toEqual([1, 2, 1]);
    await recorded.dispose();
  });
});

function deferred<T>(): {
  promise: Promise<T>;
  resolve(value: T): void;
} {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}
