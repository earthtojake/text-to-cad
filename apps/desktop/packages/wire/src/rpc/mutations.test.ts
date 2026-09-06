import { ok } from '@emdash/shared';
import { retrySchedule } from '@emdash/shared/scheduling';
import { deferred, waitFor } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import type { LiveModelClientHandle } from '../api/client';
import { connect } from '../api/connect';
import {
  defineContract,
  liveModel,
  liveState,
  mutation,
  type LiveModelKey,
  type LiveModelDef,
} from '../api/define';
import type { WireInstrumentation } from '../api/instrumentation';
import { serve } from '../api/serve';
import {
  memoryTransportPair,
  reconnectingTransport,
  type MemoryTransportPair,
} from '../api/transports';
import { createLiveModelReplicaCache } from '../live/replica';
import { expose } from '../state/bridge/expose';
import { cell, snapshot } from '../state/core';
import { createTestWire } from '../testing';
import { client } from './client';
import { createController } from './controller';

const keySchema = z.object({ id: z.string() });
const stateSchema = z.object({ count: z.number() });

function setup(instrumentation?: WireInstrumentation) {
  let handlerCalls = 0;
  const contract = createCounterContract();
  const left = cell({ count: 0 });
  const right = cell({ count: 10 });
  const provider = expose(
    contract.counter,
    { left: () => left, right: () => right },
    {
      instrumentation,
      mutations: {
        async bump(context) {
          handlerCalls += 1;
          const touched = ['left'];
          const leftRevision = left.update((previous) => ({ count: previous.count + 1 }), {
            mutationIds: [context.mutationId],
          });
          const observations = [context.observed('left', leftRevision)];
          if (context.input.touchRight) {
            const rightRevision = right.update((previous) => ({ count: previous.count + 1 }), {
              mutationIds: [context.mutationId],
            });
            observations.push(context.observed('right', rightRevision));
            touched.push('right');
          }
          await Promise.all(observations);
          return ok({ touched });
        },
      },
    }
  );
  const key = { id: 'shared' };
  const wire = createTestWire(contract, { counter: provider });
  return {
    client: wire.client,
    key,
    left,
    right,
    calls: () => handlerCalls,
  };
}

describe('live model group mutations', () => {
  it('settles only the live models actually touched by a mutation', async () => {
    const { client, key } = setup();
    const { instance: counter, dispose } = await acquireCounter(client.counter, key);

    const first = await counter.mutations.bump({ touchRight: false });
    expect(first.result).toMatchObject({ success: true, data: { data: { touched: ['left'] } } });
    await first.settled;
    expect(counter.states.left.current()).toEqual({ count: 1 });
    expect(counter.states.right.current()).toEqual({ count: 10 });

    const second = await counter.mutations.bump({ touchRight: true });
    await second.settled;
    expect(counter.states.left.current()).toEqual({ count: 2 });
    expect(counter.states.right.current()).toEqual({ count: 11 });
    await dispose();
  });

  it('settles touched models through the materialized instance', async () => {
    const { client, key } = setup();
    const { instance: counter, dispose } = await acquireCounter(client.counter, key);
    await counter.states.left.ready;

    const invocation = await counter.mutations.bump({ touchRight: true });
    await invocation.settled;
    expect(counter.states.left.current()).toEqual({ count: 1 });
    expect(counter.states.right.current()).toEqual({ count: 11 });
    await dispose();
  });

  it('dedupes duplicate group mutation ids', async () => {
    const dedupes: unknown[] = [];
    const { client, key, left, calls } = setup({
      mutationDeduped: (event) => dedupes.push(event),
    });
    const { instance: counter, dispose } = await acquireCounter(client.counter, key);

    const first = await counter.mutations.bump({ touchRight: false }, { mutationId: 'same' });
    const second = await counter.mutations.bump({ touchRight: false }, { mutationId: 'same' });

    expect(first.result).toEqual(second.result);
    expect(snapshot(left).value).toEqual({ count: 1 });
    expect(calls()).toBe(1);
    expect(dedupes).toEqual([{ mutationId: 'same', path: 'counter.bump' }]);
    await dispose();
  });

  it('retries disconnected mutations with the same mutation id', async () => {
    let handlerCalls = 0;
    const gate = deferred<void>();
    const contract = createCounterContract();
    const left = cell({ count: 0 });
    const right = cell({ count: 0 });
    const provider = expose(
      contract.counter,
      { left: () => left, right: () => right },
      {
        mutations: {
          async bump(context) {
            handlerCalls += 1;
            const revision = left.update((previous) => ({ count: previous.count + 1 }), {
              mutationIds: [context.mutationId],
            });
            await gate.promise;
            await context.observed('left', revision);
            return ok({ touched: ['left'] });
          },
        },
      }
    );
    const key = { id: 'shared' };
    let currentPair: MemoryTransportPair | undefined;
    const controller = createController(contract, { counter: provider });
    const transport = reconnectingTransport(
      async () => {
        currentPair = memoryTransportPair();
        serve(currentPair.right, controller);
        return currentPair.left;
      },
      { backoffMs: [0] }
    );
    const contractClient = client(contract, connect(transport));
    const { instance: counter, dispose } = await acquireCounter(contractClient.counter, key);

    const invocation = counter.mutations.bump(
      { touchRight: false },
      {
        mutationId: 'retry-mutation',
        retry: { schedule: retrySchedule({ delaysMs: [0], maxRetries: 1 }) },
      }
    );
    await waitFor(() => handlerCalls === 1 && currentPair !== undefined);
    currentPair?.disconnect();
    gate.resolve();

    await expect(invocation).resolves.toMatchObject({
      result: { success: true },
    });
    expect(snapshot(left).value).toEqual({ count: 1 });
    expect(handlerCalls).toBe(1);
    await dispose();
    transport.close();
  });
});

async function acquireCounter<Group extends LiveModelDef>(
  group: LiveModelClientHandle<Group>,
  key: LiveModelKey<Group>
) {
  const replica = createLiveModelReplicaCache(group.def, group);
  const lease = replica.acquire(key);
  const instance = await lease.ready();
  return {
    instance,
    async dispose() {
      await lease.release();
      await replica.dispose();
    },
  };
}

function createCounterContract() {
  return defineContract({
    counter: liveModel({
      key: keySchema,
      states: {
        left: liveState({ data: stateSchema }),
        right: liveState({ data: stateSchema }),
      },
      mutations: {
        bump: mutation({
          input: z.object({ touchRight: z.boolean() }),
          data: z.object({ touched: z.array(z.string()) }),
          error: z.string(),
        }),
      },
    }),
  });
}
