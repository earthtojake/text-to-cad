import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import type { LiveSource } from '../api/channel';
import {
  defineContract,
  eventStream,
  liveModel,
  liveState,
  liveLog,
  procedure,
} from '../api/define';
import { WireError } from '../api/protocol';
import { encodeTopic, splitTopic } from '../api/topics';
import { createController } from './controller';

const keySchema = z.object({ id: z.string() });
const stateSchema = z.object({ count: z.number() });
const outputSchema = z.object({ value: z.string() });

function makeContract() {
  return defineContract({
    echo: procedure({ input: z.object({ value: z.string() }), output: outputSchema }),
    state: liveModel({ key: keySchema, states: { state: liveState({ data: stateSchema }) } }),
    output: liveLog({ key: keySchema }),
  });
}

function stubSource(data: unknown): LiveSource {
  return {
    snapshot: () => ({ generation: 1, sequence: 0, timestamp: 0, data }),
    subscribe: vi.fn(() => vi.fn()),
  };
}

function stateProvider(
  def: ReturnType<typeof makeContract>['state'],
  entries: Record<string, LiveSource>
) {
  return {
    kind: 'liveModelProvider' as const,
    contract: def,
    resolveState: (key: { id: string }) => entries[key.id],
    runMutation: async (): Promise<never> => {
      throw new WireError('UNKNOWN_PROCEDURE', 'no mutations');
    },
  };
}

describe('createController', () => {
  it('validates inputs and outputs according to policy', async () => {
    const contract = makeContract();
    const controller = createController(
      contract,
      {
        echo: (input) => ({ value: input.value.toUpperCase() }),
        state: stateProvider(contract.state, {}),
        output: () => null,
      },
      { validate: 'full' }
    );

    await expect(controller.call('echo', { value: 'ok' })).resolves.toEqual({ value: 'OK' });
    await expect(controller.call('echo', { value: 1 })).rejects.toThrow();
  });

  it('routes live topics through encoded keys', () => {
    const contract = makeContract();
    const controller = createController(contract, {
      echo: (input) => ({ value: input.value }),
      state: stateProvider(contract.state, { known: stubSource({ count: 1 }) }),
      output: () => null,
    });

    const source = controller.resolveLive(
      encodeTopic(contract.state.states.state.id, { id: 'known' })
    );
    expect(source?.snapshot()).toMatchObject({ data: { count: 1 } });
    expect(
      controller.resolveLive(encodeTopic(contract.state.states.state.id, { id: 'missing' }))
        ?.snapshot
    ).toThrow(/Unknown live topic/);
  });

  it('requires live model providers', () => {
    const contract = makeContract();
    expect(() =>
      createController(contract, {
        echo: (input) => ({ value: input.value }),
        output: () => null,
      })
    ).toThrow(/requires a provider or client handle/);
  });

  it('roundtrips topic encoding including undefined keys', () => {
    expect(splitTopic(encodeTopic('global.model', undefined))).toEqual({
      refId: 'global.model',
      rawKey: undefined,
    });
    expect(splitTopic(encodeTopic('keyed.model', { b: 2, a: 1 }))).toEqual({
      refId: 'keyed.model',
      rawKey: { a: 1, b: 2 },
    });
  });

  it('binds nested contracts using object keys as paths', async () => {
    const child = makeContract();
    const contract = defineContract({ child });
    const controller = createController(contract, {
      child: {
        echo: (input) => ({ value: `child:${input.value}` }),
        state: stateProvider(contract.child.state, { known: stubSource({ count: 3 }) }),
        output: () => null,
      },
    });

    expect(child.state.id).toBe('state');
    expect(child.state.states.state.id).toBe('state.state');
    expect(contract.child.state.id).toBe('child.state');
    expect(contract.child.state.states.state.id).toBe('child.state.state');
    expect(contract.child.output.id).toBe('child.output');
    await expect(controller.call('child.echo', { value: 'x' })).resolves.toEqual({
      value: 'child:x',
    });
    expect(
      controller
        .resolveLive(encodeTopic(contract.child.state.states.state.id, { id: 'known' }))
        ?.snapshot()
    ).toMatchObject({ data: { count: 3 } });
  });

  it('supports async resolveState in a LiveModelProvider', async () => {
    const contract = makeContract();
    const source = stubSource({ count: 42 });
    const controller = createController(contract, {
      echo: (input) => ({ value: input.value }),
      state: {
        kind: 'liveModelProvider' as const,
        contract: contract.state,
        resolveState: async () => source,
        runMutation: async () => ({ success: true as const, data: { data: {}, cursors: [] } }),
      },
      output: () => null,
    });

    const topic = encodeTopic(contract.state.states.state.id, { id: 'x' });
    const resolved = controller.resolveLive(topic);
    expect(resolved).not.toBeNull();
    await expect(resolved!.snapshot()).resolves.toMatchObject({ data: { count: 42 } });

    const lease = controller.acquireLive(topic);
    expect(lease).not.toBeNull();
    const leased = await lease!.ready();
    expect(leased.snapshot()).toMatchObject({ data: { count: 42 } });
    await lease!.release();
  });

  it('handles async-null resolveState as a missing live source', async () => {
    const contract = makeContract();
    const controller = createController(contract, {
      echo: (input) => ({ value: input.value }),
      state: {
        kind: 'liveModelProvider' as const,
        contract: contract.state,
        resolveState: async () => null,
        runMutation: async () => ({ success: true as const, data: { data: {}, cursors: [] } }),
      },
      output: () => null,
    });

    const topic = encodeTopic(contract.state.states.state.id, { id: 'x' });
    const resolved = controller.resolveLive(topic);
    expect(resolved).not.toBeNull();
    await expect(resolved!.snapshot()).rejects.toThrow(/Unknown live topic/);
  });

  it('supports async event stream resolver', async () => {
    const eventsContract = defineContract({
      events: eventStream({ key: keySchema, event: z.object({ msg: z.string() }) }),
    });
    const source = stubSource({ msg: 'hello' });
    const controller = createController(eventsContract, {
      events: async () => source,
    });

    const topic = encodeTopic(eventsContract.events.id, { id: 'a' });
    const resolved = controller.resolveLive(topic);
    expect(resolved).not.toBeNull();
    await expect(resolved!.snapshot()).resolves.toMatchObject({ data: { msg: 'hello' } });
  });

  it('supports async live log resolver', async () => {
    const contract = makeContract();
    const source = stubSource({ line: 'output' });
    const controller = createController(contract, {
      echo: (input) => ({ value: input.value }),
      state: stateProvider(contract.state, {}),
      output: async () => source,
    });

    const topic = encodeTopic(contract.output.id, { id: 'b' });
    const resolved = controller.resolveLive(topic);
    expect(resolved).not.toBeNull();
    await expect(resolved!.snapshot()).resolves.toMatchObject({ data: { line: 'output' } });
  });
});
