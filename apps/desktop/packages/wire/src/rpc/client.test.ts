import { ok } from '@emdash/shared';
import { waitFor } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { defineContract, liveModel, liveState, liveLog, mutation, procedure } from '../api/define';
import { WireError } from '../api/protocol';
import { encodeTopic } from '../api/topics';
import { LiveLogSource } from '../live/log';
import { createLiveModelReplicaCache, ReplicaState } from '../live/replica';
import { LiveStateSource } from '../live/state/source';
import { expose } from '../state/bridge/expose';
import { cell } from '../state/core';
import { createTestWire } from '../testing';

const stateSchema = z.object({ count: z.number() });
const keySchema = z.object({ id: z.string() });

const contract = defineContract({
  increment: procedure({ input: keySchema, output: stateSchema }),
  state: liveModel({ key: keySchema, states: { state: liveState({ data: stateSchema }) } }),
  output: liveLog({ key: keySchema }),
});

function taskStateProvider(def: typeof contract.state, model: LiveStateSource<{ count: number }>) {
  return {
    kind: 'liveModelProvider' as const,
    contract: def,
    resolveState: (key: { id: string }) => (key.id === 'task' ? model : undefined),
    runMutation: async (): Promise<never> => {
      throw new WireError('UNKNOWN_PROCEDURE', 'no mutations');
    },
  };
}

describe('client', () => {
  it('calls typed procedures and exposes live client handles', async () => {
    const model = new LiveStateSource({ count: 0 });
    const log = new LiveLogSource({ generation: 2000 });
    const { client: contractClient } = createTestWire(contract, {
      increment: () => {
        model.produce((draft) => {
          draft.count += 1;
        });
        log.append('incremented\n');
        return model.snapshot().data;
      },
      state: taskStateProvider(contract.state, model),
      output: () => log,
    });

    const seenStates: Array<{ count: number }> = [];
    const state = new ReplicaState(contractClient.state.state({ id: 'task' }, 'state'), {
      schema: stateSchema,
      onChange: (value) => seenStates.push(value),
    });
    const appended: string[] = [];
    const resets: string[] = [];
    const output = contractClient.output.handle({ id: 'task' });

    await state.ready;
    resets.push((await output.snapshot()).data.text);
    const detachLog = await output.attach((update) => {
      const delta = update.delta as { chunk: string };
      appended.push(delta.chunk);
    });
    await expect(contractClient.increment({ id: 'task' })).resolves.toEqual({ count: 1 });
    await waitFor(() => state.current().count === 1 && appended.length === 1);

    expect(seenStates.at(-1)).toEqual({ count: 1 });
    expect(appended).toEqual(['incremented\n']);
    expect(resets).toEqual(['']);

    await state.dispose();
    detachLog();
  });

  it('builds nested clients using object keys as call paths', async () => {
    const nested = defineContract({ child: contract });
    const model = new LiveStateSource({ count: 0 });
    const log = new LiveLogSource({ generation: 2000 });
    const { client: contractClient } = createTestWire(nested, {
      child: {
        increment: () => {
          model.produce((draft) => {
            draft.count += 1;
          });
          log.append('incremented\n');
          return model.snapshot().data;
        },
        state: taskStateProvider(nested.child.state, model),
        output: () => log,
      },
    });

    const state = new ReplicaState(contractClient.child.state.state({ id: 'task' }, 'state'), {
      schema: stateSchema,
    });
    await state.ready;
    await expect(contractClient.child.increment({ id: 'task' })).resolves.toEqual({ count: 1 });
    await waitFor(() => state.current().count === 1);
    await state.dispose();
  });

  it('uses caller-supplied mutation IDs for group mutations', async () => {
    const groupContract = defineContract({
      conversation: liveModel({
        key: keySchema,
        states: {
          state: liveState({ data: stateSchema }),
        },
        mutations: {
          bump: mutation({ input: z.object({}), data: z.void(), error: z.string() }),
        },
      }),
    });
    const key = { id: 'task' };
    const base = cell({ count: 0 });
    const provider = expose(
      groupContract.conversation,
      { state: () => base },
      {
        mutations: {
          async bump(context) {
            const revision = base.update((previous) => ({ count: previous.count + 1 }), {
              mutationIds: [context.mutationId],
            });
            await context.observed('state', revision);
            return ok(undefined);
          },
        },
      }
    );

    const wire = createTestWire(groupContract, { conversation: provider });
    const sourceLease = wire.controller.acquireLive(
      encodeTopic(groupContract.conversation.states.state.id, key)
    );
    expect(sourceLease).not.toBeNull();
    const source = await sourceLease!.ready();
    const updates: unknown[] = [];
    source.subscribe((update) => updates.push(update));

    const replica = createLiveModelReplicaCache(
      wire.client.conversation.def,
      wire.client.conversation
    );
    const lease = replica.acquire(key);
    const binding = await lease.ready();

    await binding.ready;
    const invocation = await binding.mutations.bump({}, { mutationId: 'custom-mutation' });
    await invocation.settled;

    expect(updates).toMatchObject([{ mutationIds: ['custom-mutation'] }]);
    await lease.release();
    await replica.dispose();
    await sourceLease!.release();
    await provider.dispose();
  });
});
