import { ok } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import { createManualClock } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { liveModel, liveState, mutation } from '../api';
import type { LiveUpdate } from '../api/channel';
import type { LiveModelClientHandle } from '../api/client';
import { LiveStateSource } from '../live/state/source';
import {
  batch,
  cell,
  derived,
  expose,
  flushStateTurn,
  observe,
  optimistic,
  pin,
  pokeChannel,
  query,
  remote,
  snapshot,
} from './index';

describe('wire state primitives', () => {
  it('batches writes and publishes a derived value once per turn', () => {
    const scope = createScope();
    const left = cell(1);
    const right = cell(2);
    const total = derived(() => snapshot(left).value + snapshot(right).value);
    const seen: number[] = [];

    observe(total, (current) => seen.push(current.value ?? -1), { scope });

    batch(() => {
      left.set(3);
      right.set(4);
    });
    flushStateTurn();

    expect(seen).toEqual([3, 7]);
    void scope.dispose();
  });

  it('refreshes query values from pokes and settles known writes without refetching', async () => {
    const scope = createScope();
    const clock = createManualClock();
    const channel = pokeChannel('counter');
    let source = 1;
    let fetchCount = 0;
    const counter = query({
      fetch: async () => {
        fetchCount += 1;
        return source;
      },
      pokes: [channel.subscription()],
      debounceMs: 5,
      clock,
      scope,
    });
    const seen: Array<number | undefined> = [];

    observe(counter, (current) => seen.push(current.value), { scope });
    await clock.advanceBy(5);

    source = 2;
    channel.poke();
    await clock.advanceBy(5);
    counter.settle(3, { mutationIds: ['m1'] });
    flushStateTurn();

    expect(fetchCount).toBe(2);
    expect(seen).toEqual([undefined, 1, 1, 2, 3]);
    expect(snapshot(counter).mutationIds).toEqual(['m1']);
    await scope.dispose();
  });

  it('overlays optimistic patches until the base acknowledges the mutation', () => {
    const scope = createScope();
    const base = cell({ count: 1 });
    const view = optimistic(base);
    const seen: number[] = [];

    observe(view, (current) => seen.push(current.value?.count ?? -1), { scope });
    view.apply(
      (draft) => {
        draft.count += 1;
      },
      { mutationId: 'm1' }
    );
    flushStateTurn();
    base.set({ count: 2 }, { mutationIds: ['m1'] });
    flushStateTurn();

    expect(seen).toEqual([1, 2, 2]);
    expect(snapshot(view).value?.count).toBe(2);
    void scope.dispose();
  });

  it('pins nodes and aggregates loading status', async () => {
    const scope = createScope();
    const clock = createManualClock();
    const model = query({
      fetch: async () => 'ready',
      debounceMs: 10,
      clock,
      scope,
    });

    const pins = pin(scope, [model]);
    expect(pins.status).toBe('loading');
    await clock.advanceBy(10);
    flushStateTurn();

    expect(pins.status).toBe('live');
    await expect(pins.settled()).resolves.toBeUndefined();
    await scope.dispose();
  });

  it('exposes state and waits for mutation-observed revisions', async () => {
    const contract = liveModel({
      key: z.object({ id: z.string() }),
      states: {
        value: liveState({ data: z.object({ count: z.number() }) }),
      },
      mutations: {
        increment: mutation({
          input: z.object({ by: z.number() }),
          data: z.void(),
          error: z.never(),
        }),
      },
    });
    const model = cell({ count: 0 });
    const provider = expose(
      contract,
      { value: model },
      {
        mutations: {
          async increment(context) {
            const revision = model.update(
              (previous) => ({ count: previous.count + context.input.by }),
              {
                mutationIds: [context.mutationId],
              }
            );
            await context.observed('value', revision);
            return ok<void>();
          },
        },
      }
    );

    const lease = provider.acquireState({ id: 'one' }, 'value');
    const source = await lease.ready();
    const result = await provider.runMutation('increment', {
      key: { id: 'one' },
      input: { by: 2 },
      mutationId: 'm1',
    });
    flushStateTurn();
    const current = await source.snapshot();

    expect(result.success).toBe(true);
    if (!result.success) throw new Error('Expected mutation to succeed');
    expect(result.data.cursors).toHaveLength(1);
    expect(current.data).toEqual({ count: 2 });
    await lease.release();
    await provider.dispose();
  });

  it('wraps a live model client as remote readable state', async () => {
    const contract = liveModel({
      key: z.object({ id: z.string() }),
      states: {
        value: liveState({ data: z.object({ count: z.number() }) }),
      },
      mutations: {},
    });
    const upstream = new LiveStateSource({ count: 1 });
    const scope = createScope();
    const client = {
      kind: 'liveModelClientHandle',
      def: contract,
      state: () => ({
        topic: 'test',
        snapshot: () => Promise.resolve(upstream.snapshot()),
        attach: async (push: (update: LiveUpdate) => void) => upstream.subscribe(push),
        asLiveSource: () => upstream,
      }),
      mutate: async () => {
        throw new Error('not implemented');
      },
    } as unknown as LiveModelClientHandle<typeof contract>;
    const model = remote(contract, client);
    const member = model({ id: 'one' });
    const seen: Array<number | undefined> = [];

    observe(member.states.value, (current) => seen.push(current.value?.count), { scope });
    await waitForValue(() => snapshot(member.states.value).value?.count, 1);
    upstream.replace({ count: 2 }, { mutationIds: ['m1'] });
    await flushAsync();
    flushStateTurn();

    expect(seen).toEqual([undefined, 1, 2]);
    expect(snapshot(member.states.value).mutationIds).toEqual(['m1']);
    await scope.dispose();
    await model.dispose();
  });
});

async function flushAsync(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

async function waitForValue<T>(readValue: () => T, expected: T): Promise<void> {
  for (let index = 0; index < 10; index += 1) {
    await flushAsync();
    flushStateTurn();
    if (Object.is(readValue(), expected)) return;
  }
  expect(readValue()).toBe(expected);
}
