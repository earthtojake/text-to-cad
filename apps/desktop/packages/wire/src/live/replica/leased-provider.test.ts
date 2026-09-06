import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import {
  connect,
  defineContract,
  encodeTopic,
  liveModel,
  liveState,
  memoryTransportPair,
  serve,
} from '../../api';
import { client } from '../../rpc/client';
import { createController } from '../../rpc/controller';
import { LiveStateSource } from '../state';
import type { LeasedLiveModelProvider } from './leased-provider';

describe('LeasedLiveModelProvider', () => {
  it('acquires and releases a live source through the controller seam', async () => {
    const contract = defineContract({
      item: liveModel({
        key: z.object({ path: z.string() }),
        states: { value: liveState({ data: z.object({ count: z.number() }) }) },
      }),
    });
    const state = new LiveStateSource({ count: 1 }, 1000);
    const release = vi.fn(async () => {});
    const provider: LeasedLiveModelProvider<typeof contract.item> = {
      kind: 'leasedLiveModelProvider',
      contract: contract.item,
      acquireState: () => ({ ready: async () => state, release }),
      runMutation: async () => {
        throw new Error('no mutations');
      },
      dispose: async () => {},
    };
    const controller = createController(contract, { item: provider });
    const topic = encodeTopic(contract.item.states.value.id, { path: '/repo' });

    expect(controller.resolveLive(topic)).toBeNull();
    const lease = controller.acquireLive(topic);
    expect(lease).not.toBeNull();
    await expect(lease?.ready()).resolves.toBe(state);
    await lease?.release();
    expect(release).toHaveBeenCalledOnce();
  });

  it('releases snapshot leases after the response', async () => {
    const contract = defineContract({
      item: liveModel({
        key: z.object({ path: z.string() }),
        states: { value: liveState({ data: z.object({ count: z.number() }) }) },
      }),
    });
    const release = vi.fn(async () => {});
    const provider: LeasedLiveModelProvider<typeof contract.item> = {
      kind: 'leasedLiveModelProvider',
      contract: contract.item,
      acquireState: () => ({
        ready: async () => new LiveStateSource({ count: 1 }),
        release,
      }),
      runMutation: async () => {
        throw new Error('no mutations');
      },
      dispose: async () => {},
    };
    const pair = memoryTransportPair();
    const stop = serve(pair.right, createController(contract, { item: provider }));
    const remote = client(contract, connect(pair.left));

    try {
      await expect(remote.item.state({ path: '/repo' }, 'value').snapshot()).resolves.toMatchObject(
        {
          data: { count: 1 },
        }
      );
      expect(release).toHaveBeenCalledOnce();
    } finally {
      stop();
    }
  });

  it('retains attachment leases until detach', async () => {
    const contract = defineContract({
      item: liveModel({
        key: z.object({ path: z.string() }),
        states: { value: liveState({ data: z.object({ count: z.number() }) }) },
      }),
    });
    const release = vi.fn(async () => {});
    const state = new LiveStateSource({ count: 1 });
    const provider: LeasedLiveModelProvider<typeof contract.item> = {
      kind: 'leasedLiveModelProvider',
      contract: contract.item,
      acquireState: () => ({ ready: async () => state, release }),
      runMutation: async () => {
        throw new Error('no mutations');
      },
      dispose: async () => {},
    };
    const pair = memoryTransportPair();
    const stop = serve(pair.right, createController(contract, { item: provider }));
    const remote = client(contract, connect(pair.left));

    try {
      const detach = await remote.item.state({ path: '/repo' }, 'value').attach(() => {});
      expect(release).not.toHaveBeenCalled();
      await detach();
      expect(release).toHaveBeenCalledOnce();
    } finally {
      stop();
    }
  });
});
