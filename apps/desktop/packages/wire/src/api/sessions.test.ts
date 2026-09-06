import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { createController } from '../rpc/controller';
import type { LiveSource, LiveUpdate } from './channel';
import { connect } from './connect';
import { defineContract, liveModel, liveState } from './define';
import { createWireSessionHub } from './sessions';
import { encodeTopic } from './topics';
import { memoryTransportPair } from './transports';

const contract = defineContract({
  state: liveModel({
    key: z.object({ id: z.string() }),
    states: { state: liveState({ data: z.object({ count: z.number() }) }) },
  }),
});

function makeSource() {
  const subscribers = new Set<(update: LiveUpdate) => void>();
  const unsubscribes: Array<ReturnType<typeof vi.fn>> = [];
  const source: LiveSource = {
    snapshot: () => ({ generation: 1, sequence: 0, timestamp: 0, data: { count: 0 } }),
    subscribe: (cb) => {
      subscribers.add(cb);
      const unsubscribe = vi.fn(() => subscribers.delete(cb));
      unsubscribes.push(unsubscribe);
      return unsubscribe;
    },
  };
  return { source, subscribers, unsubscribes };
}

describe('createWireSessionHub', () => {
  it('serves multiple sessions and closes only the matching subscriptions', async () => {
    const live = makeSource();
    const controller = createController(contract, {
      state: {
        kind: 'liveModelProvider',
        contract: contract.state,
        resolveState: () => live.source,
        runMutation: async () => {
          throw new Error('No mutations');
        },
      },
    });
    const hub = createWireSessionHub(controller);
    const first = memoryTransportPair();
    const second = memoryTransportPair();
    hub.open('first', first.right);
    hub.open('second', second.right);
    const firstClient = connect(first.left);
    const secondClient = connect(second.left);
    const topic = encodeTopic(contract.state.states.state.id, { id: 'same' });

    await firstClient.attach(topic, () => {});
    await secondClient.attach(topic, () => {});
    expect(live.subscribers.size).toBe(2);

    hub.close('first');
    expect(live.unsubscribes[0]).toHaveBeenCalledTimes(1);
    expect(live.subscribers.size).toBe(1);

    await hub.dispose();
    expect(live.unsubscribes[1]).toHaveBeenCalledTimes(1);
    expect(live.subscribers.size).toBe(0);
  });

  it('replaces an existing session id and auto-closes on disconnect', async () => {
    const live = makeSource();
    const hub = createWireSessionHub(
      createController(contract, {
        state: {
          kind: 'liveModelProvider',
          contract: contract.state,
          resolveState: () => live.source,
          runMutation: async () => {
            throw new Error('No mutations');
          },
        },
      })
    );
    const original = memoryTransportPair();
    const replacement = memoryTransportPair();
    const topic = encodeTopic(contract.state.states.state.id, { id: 'same' });

    hub.open('window', original.right);
    await connect(original.left).attach(topic, () => {});
    expect(live.subscribers.size).toBe(1);

    hub.open('window', replacement.right);
    expect(live.subscribers.size).toBe(0);

    await connect(replacement.left).attach(topic, () => {});
    expect(live.subscribers.size).toBe(1);
    replacement.disconnect();
    expect(live.subscribers.size).toBe(0);
  });
});
