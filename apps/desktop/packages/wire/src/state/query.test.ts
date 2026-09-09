import { createScope, type Scope } from '@emdash/shared/concurrency';
import { createManualClock } from '@emdash/shared/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { snapshot } from './core';
import { pokeChannel } from './poke';
import { query } from './query';
import { createRecordingLane, recordSnapshots, settleAsync } from './testing';

describe('state query', () => {
  let scope: Scope;

  beforeEach(() => {
    scope = createScope();
  });

  afterEach(async () => {
    await scope.dispose();
  });
  it('coalesces multiple pokes inside the debounce window into one fetch', async () => {
    const clock = createManualClock();
    const channel = pokeChannel('query-debounce');
    let source = 1;
    let fetchCount = 0;
    const model = query({
      fetch: async () => {
        fetchCount += 1;
        return source;
      },
      pokes: [channel.subscription()],
      debounceMs: 5,
      clock,
      scope,
    });
    const recorded = recordSnapshots(model);

    await clock.advanceBy(5);
    await settleAsync();
    expect(snapshot(model).value).toBe(1);
    expect(fetchCount).toBe(1);

    source = 2;
    channel.poke();
    await clock.advanceBy(2);
    channel.poke();
    await clock.advanceBy(2);
    channel.poke();
    await clock.advanceBy(5);
    await settleAsync();

    expect(snapshot(model).value).toBe(2);
    expect(fetchCount).toBe(2);
    expect(recorded.snapshots.map((current) => current.value)).toEqual([undefined, 1, 1, 2]);
    expect(recorded.snapshots.map((current) => current.status)).toEqual([
      'loading',
      'live',
      'stale',
      'live',
    ]);
    await recorded.dispose();
  });

  it('does not publish when a refresh returns an equal value', async () => {
    const model = query({
      fetch: async () => ({ count: 1 }),
      debounceMs: 0,
      scope,
    });
    const recorded = recordSnapshots(model);

    await model.refresh();
    await settleAsync();
    const revision = snapshot(model).revision;

    await model.refresh();
    await settleAsync();

    expect(snapshot(model).revision).toBe(revision);
    expect(recorded.snapshots.map((current) => current.value)).toEqual([undefined, { count: 1 }]);
    await recorded.dispose();
  });

  it('tags a refreshed snapshot with mutation ids', async () => {
    let source = 1;
    const model = query({
      fetch: async () => source,
      debounceMs: 0,
      scope,
    });
    const recorded = recordSnapshots(model);

    await model.refresh();
    source = 2;
    await model.refresh({ mutationIds: ['m2'] });
    await settleAsync();

    expect(snapshot(model)).toMatchObject({ value: 2, mutationIds: ['m2'] });
    expect(recorded.snapshots.map((current) => current.mutationIds)).toEqual([
      undefined,
      undefined,
      ['m2'],
    ]);
    await recorded.dispose();
  });

  it('keeps settled writes when an older in-flight fetch resolves', async () => {
    const clock = createManualClock();
    const pending = deferred<number>();
    const model = query({
      fetch: () => pending.promise,
      debounceMs: 0,
      clock,
      scope,
    });
    const recorded = recordSnapshots(model);

    await clock.advanceBy(0);
    model.settle(2, { mutationIds: ['m1'] });
    pending.resolve(1);
    await settleAsync();

    expect(snapshot(model)).toMatchObject({
      value: 2,
      status: 'live',
      mutationIds: ['m1'],
    });
    expect(recorded.snapshots.map((current) => current.value)).toEqual([undefined, 2]);
    await recorded.dispose();
  });

  it('refetches once after a poke arrives during an in-flight fetch', async () => {
    const clock = createManualClock();
    const channel = pokeChannel('query-race');
    const first = deferred<number>();
    const second = deferred<number>();
    const fetches: Array<Promise<number>> = [first.promise, second.promise];
    const model = query({
      fetch: () => fetches.shift() ?? Promise.resolve(99),
      pokes: [channel.subscription()],
      debounceMs: 0,
      clock,
      scope,
    });
    const recorded = recordSnapshots(model);

    await clock.advanceBy(0);
    channel.poke();
    first.resolve(1);
    await settleAsync();
    await clock.advanceBy(0);
    second.resolve(2);
    await settleAsync();

    expect(snapshot(model).value).toBe(2);
    expect(recorded.snapshots.map((current) => current.value)).toEqual([undefined, 1, 2]);
    await recorded.dispose();
  });

  it('moves to error and retries on the next poke', async () => {
    const clock = createManualClock();
    const channel = pokeChannel('query-error');
    let attempt = 0;
    const errors: unknown[] = [];
    const model = query({
      async fetch() {
        attempt += 1;
        if (attempt === 1) throw new Error('temporary');
        return 'ok';
      },
      pokes: [channel.subscription()],
      debounceMs: 0,
      clock,
      scope,
      onError: (error) => errors.push(error),
    });
    const recorded = recordSnapshots(model);

    await clock.advanceBy(0);
    await settleAsync();
    expect(snapshot(model).status).toBe('error');

    channel.poke();
    await clock.advanceBy(0);
    await settleAsync();

    expect(snapshot(model)).toMatchObject({ value: 'ok', status: 'live' });
    expect(errors).toHaveLength(1);
    expect(recorded.snapshots.map((current) => current.status)).toContain('error');
    await recorded.dispose();
  });

  it('revalidates only while observed and disposes with its scope', async () => {
    const clock = createManualClock();
    const queryScope = createScope();
    let source = 1;
    let fetchCount = 0;
    const model = query({
      fetch: async () => {
        fetchCount += 1;
        return source;
      },
      debounceMs: 0,
      revalidateEveryMs: 10,
      clock,
      scope: queryScope,
    });
    const recorded = recordSnapshots(model);

    await clock.advanceBy(0);
    source = 2;
    await clock.advanceBy(10);
    await settleAsync();
    expect(snapshot(model).value).toBe(2);

    await queryScope.dispose();
    source = 3;
    await clock.advanceBy(20);
    expect(fetchCount).toBe(2);
    await recorded.dispose();
  });

  it('runs refresh work through the configured lane', async () => {
    const lane = createRecordingLane();
    const model = query({
      fetch: async () => 1,
      lane,
      scope,
    });

    await model.refresh();

    expect(lane.runs).toEqual([1]);
  });

  it('delivers mutation ids from a refresh superseded by a settle', async () => {
    const clock = createManualClock();
    const pending = deferred<number>();
    let fetchIndex = 0;
    const model = query({
      fetch: () => (fetchIndex++ === 0 ? Promise.resolve(1) : pending.promise),
      debounceMs: 0,
      clock,
      scope,
    });

    await model.refresh();
    const superseded = model.refresh({ mutationIds: ['m1'] });
    model.settle(5, { mutationIds: ['s1'] });
    pending.resolve(2);
    await superseded;
    await settleAsync();

    const current = snapshot(model);
    expect(current.value).toBe(5);
    expect(current.mutationIds).toContain('m1');
    expect(current.mutationIds).toContain('s1');
  });

  it('delivers mutation ids from a refresh superseded by an invalidation', async () => {
    const clock = createManualClock();
    const pending = deferred<number>();
    let fetchIndex = 0;
    const model = query({
      fetch: () => (fetchIndex++ === 0 ? Promise.resolve(1) : pending.promise),
      debounceMs: 0,
      clock,
      scope,
    });

    await model.refresh();
    const superseded = model.refresh({ mutationIds: ['m1'] });
    model.invalidate();
    pending.resolve(2);
    await superseded;
    await settleAsync();

    expect(snapshot(model).mutationIds).toContain('m1');
  });

  it('delivers every callers mutation ids across coalesced refreshes', async () => {
    const clock = createManualClock();
    const first = deferred<number>();
    const second = deferred<number>();
    const fetches = [first.promise, second.promise];
    const model = query({
      fetch: () => fetches.shift() ?? Promise.resolve(99),
      debounceMs: 0,
      clock,
      scope,
    });
    const recorded = recordSnapshots(model);

    const initial = model.refresh({ mutationIds: ['m1'] });
    const queuedOnce = model.refresh({ mutationIds: ['m2'] });
    const queuedTwice = model.refresh({ mutationIds: ['m3'] });
    expect(queuedTwice).toBe(queuedOnce);

    first.resolve(1);
    await initial;
    second.resolve(2);
    await queuedOnce;
    await settleAsync();

    const committedIds = recorded.snapshots.map((current) => current.mutationIds);
    expect(committedIds).toContainEqual(['m1']);
    expect([...(snapshot(model).mutationIds ?? [])].sort()).toEqual(['m2', 'm3']);
    await recorded.dispose();
  });

  it('carries mutation ids across a failed fetch to the next committed snapshot', async () => {
    const clock = createManualClock();
    let attempt = 0;
    const model = query({
      fetch: async () => {
        attempt += 1;
        if (attempt === 1) throw new Error('boom');
        return attempt;
      },
      debounceMs: 0,
      clock,
      scope,
    });

    await expect(model.refresh({ mutationIds: ['m1'] })).rejects.toThrow('boom');
    await model.refresh();
    await settleAsync();

    expect(snapshot(model)).toMatchObject({ value: 2, status: 'live' });
    expect(snapshot(model).mutationIds).toContain('m1');
  });
});

function deferred<T>(): {
  promise: Promise<T>;
  resolve(value: T): void;
  reject(error: unknown): void;
} {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}
