import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import type { ContractClient } from '../api/client';
import { defineContract, liveLog, liveModel, liveState, procedure } from '../api/define';
import { WireError } from '../api/protocol';
import { LiveLogSource } from '../live/log';
import { LiveStateSource } from '../live/state/source';
import { createTestWire } from '../testing';
import { queuedClient } from './queued-client';

const stateSchema = z.object({ count: z.number() });
const keySchema = z.object({ id: z.string() });

const contract = defineContract({
  increment: procedure({ input: keySchema, output: stateSchema }),
  nested: defineContract({
    echo: procedure({ input: z.string(), output: z.string() }),
  }),
  state: liveModel({ key: keySchema, states: { state: liveState({ data: stateSchema }) } }),
  output: liveLog({ key: keySchema }),
});

type Deferred<T> = {
  promise: Promise<T>;
  resolve(value: T): void;
  reject(error: unknown): void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

function createReadyWire() {
  const model = new LiveStateSource({ count: 0 });
  const log = new LiveLogSource({ generation: 2000 });
  return createTestWire(contract, {
    increment: () => {
      model.produce((draft) => {
        draft.count += 1;
      });
      return model.snapshot().data;
    },
    nested: { echo: (input: string) => input },
    state: {
      kind: 'liveModelProvider' as const,
      contract: contract.state,
      resolveState: (key: { id: string }) => (key.id === 'task' ? model : undefined),
      runMutation: async (): Promise<never> => {
        throw new WireError('UNKNOWN_PROCEDURE', 'no mutations');
      },
    },
    output: () => log,
  });
}

describe('queuedClient', () => {
  it('queues calls issued before readiness and completes them once ready', async () => {
    const ready = deferred<ContractClient<typeof contract>>();
    const queued = queuedClient(contract, () => ready.promise);

    let settled = false;
    const pendingIncrement = queued.increment({ id: 'task' }).finally(() => {
      settled = true;
    });
    const pendingEcho = queued.nested.echo('hello');

    // Nothing settles while readiness is outstanding.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(settled).toBe(false);

    const wire = createReadyWire();
    ready.resolve(wire.client);

    await expect(pendingIncrement).resolves.toEqual({ count: 1 });
    await expect(pendingEcho).resolves.toBe('hello');
  });

  it('rejects queued and future calls with the readiness failure', async () => {
    const ready = deferred<ContractClient<typeof contract>>();
    const queued = queuedClient(contract, () => ready.promise);
    const spawnError = new Error('worker spawn failed');

    const pending = queued.increment({ id: 'task' });
    ready.reject(spawnError);

    await expect(pending).rejects.toBe(spawnError);
    await expect(queued.nested.echo('again')).rejects.toBe(spawnError);
  });

  it('constructs live handles synchronously with canonical topics and defers traffic', async () => {
    const ready = deferred<ContractClient<typeof contract>>();
    const queued = queuedClient(contract, () => ready.promise);

    const wire = createReadyWire();
    const realStateHandle = wire.client.state.state({ id: 'task' }, 'state');
    const realLogHandle = wire.client.output.handle({ id: 'task' });

    const queuedStateHandle = queued.state.state({ id: 'task' }, 'state');
    const queuedLogHandle = queued.output.handle({ id: 'task' });
    expect(queuedStateHandle.topic).toBe(realStateHandle.topic);
    expect(queuedLogHandle.topic).toBe(realLogHandle.topic);
    expect(queued.state.kind).toBe('liveModelClientHandle');
    expect(queued.output.kind).toBe('liveLogClientHandle');

    const pendingSnapshot = queuedStateHandle.snapshot();
    ready.resolve(wire.client);
    expect((await pendingSnapshot).data).toEqual({ count: 0 });
    expect((await queuedLogHandle.snapshot()).data.text).toBe('');
  });

  it('invokes the readiness factory once and reuses the promise', async () => {
    let invocations = 0;
    const wire = createReadyWire();
    const queued = queuedClient(contract, () => {
      invocations += 1;
      return Promise.resolve(wire.client);
    });

    await queued.nested.echo('one');
    await queued.nested.echo('two');
    await queued.increment({ id: 'task' });
    expect(invocations).toBe(1);
  });
});
