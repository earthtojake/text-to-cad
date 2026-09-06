import { ok } from '@emdash/shared';
import { createManualClock } from '@emdash/shared/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import type { LiveClientHandle, LiveModelClientHandle } from '../../api/client';
import { defineContract, liveModel, liveState, mutation } from '../../api/define';
import { expose } from '../../state/bridge/expose';
import { cell, snapshot } from '../../state/core';
import { createTestWire } from '../../testing';
import type { LiveModelProvider } from './provider';
import { createLiveModelReplicaCache } from './replica';

const keySchema = z.object({ id: z.string() });
const stateSchema = z.object({ count: z.number() });

const api = defineContract({
  counter: liveModel({
    key: keySchema,
    states: {
      state: liveState({ data: stateSchema }),
    },
    mutations: {
      bump: mutation({
        input: z.object({}),
        data: stateSchema,
        error: z.string(),
      }),
    },
  }),
});

function counterSource(initial: { count: number }) {
  const state = cell(initial);
  const provider = expose(
    api.counter,
    { state: () => state },
    {
      mutations: {
        async bump(context) {
          let count = 0;
          const revision = state.update(
            (previous) => {
              count = previous.count + 1;
              return { count };
            },
            { mutationIds: [context.mutationId] }
          );
          await context.observed('state', revision);
          return ok({ count });
        },
      },
    }
  );
  return { state, provider };
}

describe('createLiveModelReplicaCache', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('exposes local replica state through acquired leases', async () => {
    const key = { id: 'local' };
    const { provider } = counterSource({ count: 0 });
    const upstream = createTestWire(api, { counter: provider }).client;
    const replica = createLiveModelReplicaCache(api.counter, upstream.counter);

    expect(replica.peek(key)).toBeUndefined();
    const lease = replica.acquire(key);
    const instance = await lease.ready();

    expect(instance.key).toEqual(key);
    expect(instance.states.state.current()).toEqual({ count: 0 });
    expect(replica.peek(key)).toBe(instance);

    await lease.release();
    await replica.dispose();
  });

  it('serves cached replica state and re-anchors mutation cursors', async () => {
    const key = { id: 'demo' };
    const { state, provider } = counterSource({ count: 0 });
    const upstream = createTestWire(api, { counter: provider }).client;
    const replica = createLiveModelReplicaCache(api.counter, upstream.counter, { lingerMs: 100 });
    // Replica caches are not controller impls; serving one downstream takes an
    // explicit LiveModelProvider adapter.
    const replicaProvider: LiveModelProvider<typeof api.counter> = {
      kind: 'liveModelProvider',
      contract: replica.contract,
      resolveState: (key, name) => replica.resolveState(key, name),
      runMutation: (name, envelope) => replica.runMutation(name, envelope),
    };
    const downstream = createTestWire(api, { counter: replicaProvider }).client;
    const downstreamReplica = createLiveModelReplicaCache(api.counter, downstream.counter);
    const downstreamLease = downstreamReplica.acquire(key);
    const counter = await downstreamLease.ready();

    const invocation = await counter.mutations.bump({});
    await invocation.settled;

    expect(counter.states.state.current()).toEqual({ count: 1 });
    expect(snapshot(state).value).toEqual({ count: 1 });

    await downstreamLease.release();
    await downstreamReplica.dispose();
    await replica.dispose();
  });

  it('omits settled metadata when cursor translation completes', async () => {
    const key = { id: 'settled' };
    const { provider } = counterSource({ count: 0 });
    const upstream = createTestWire(api, { counter: provider }).client;
    const replica = createLiveModelReplicaCache(api.counter, upstream.counter);
    const lease = replica.acquire(key);
    const counter = await lease.ready();

    const invocation = await counter.mutations.bump({});
    await invocation.settled;

    expect(invocation.result.success).toBe(true);
    if (invocation.result.success) {
      expect(Object.hasOwn(invocation.result.data, 'settled')).toBe(false);
    }

    await lease.release();
    await replica.dispose();
  });

  it('resolves committed mutations with settled: false when translation times out', async () => {
    const key = { id: 'timeout' };
    const clock = createManualClock();
    const cursorTranslationTimeout = vi.fn();

    const stateHandle: LiveClientHandle<{ count: number }> = {
      topic: 'counter/state',
      snapshot: async () => ({ generation: 1, sequence: 0, timestamp: 0, data: { count: 0 } }),
      // Never pushes updates, so the replica can never reach the mutation cursor.
      attach: async () => () => {},
      asLiveSource() {
        throw new Error('unused in this test');
      },
    };
    const group = {
      kind: 'liveModelClientHandle',
      def: api.counter,
      state: () => stateHandle,
      mutate: async () =>
        ok({
          data: { count: 1 },
          cursors: [
            { model: api.counter.states.state.id, key, cursor: { generation: 1, sequence: 3 } },
          ],
        }),
    } as unknown as LiveModelClientHandle<typeof api.counter>;

    const replica = createLiveModelReplicaCache(api.counter, group, {
      clock,
      instrumentation: { cursorTranslationTimeout },
    });
    const lease = replica.acquire(key);
    const counter = await lease.ready();

    const invocationPromise = counter.mutations.bump({}, { mutationId: 'mutation-1' });
    await clock.advanceBy(0);
    await clock.advanceBy(15_000);
    const invocation = await invocationPromise;

    expect(invocation.result.success).toBe(true);
    if (invocation.result.success) {
      expect(invocation.result.data.settled).toBe(false);
      expect(invocation.result.data.data).toEqual({ count: 1 });
      // Translation still yields a best-effort local cursor for the entry.
      expect(invocation.result.data.cursors).toHaveLength(1);
      expect(invocation.result.data.cursors[0].cursor.sequence).toBe(3);
    }
    expect(cursorTranslationTimeout).toHaveBeenCalledWith(
      expect.objectContaining({ model: api.counter.states.state.id, mutationId: 'mutation-1' })
    );

    await clock.advanceBy(15_000);
    await invocation.settled;

    await lease.release();
    await replica.dispose();
  });

  it('keeps warm instances visible through peek during retention', async () => {
    vi.useFakeTimers();
    const key = { id: 'retained' };
    const { provider } = counterSource({ count: 0 });
    const upstream = createTestWire(api, { counter: provider }).client;
    const replica = createLiveModelReplicaCache(api.counter, upstream.counter, { lingerMs: 50 });
    const lease = replica.acquire(key);
    const instance = await lease.ready();

    await lease.release();
    await vi.advanceTimersByTimeAsync(49);
    expect(replica.peek(key)).toBe(instance);

    await vi.advanceTimersByTimeAsync(1);
    expect(replica.peek(key)).toBeUndefined();

    await replica.dispose();
  });
});
