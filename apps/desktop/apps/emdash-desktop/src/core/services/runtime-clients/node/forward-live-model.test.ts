import type { LiveSource } from '@emdash/wire/rpc';
import { defineContract, liveModel, liveState } from '@emdash/wire/rpc';
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { forwardLiveModel } from './forward-live-model';

const contract = defineContract({
  state: liveModel({
    key: z.object({ id: z.string() }),
    states: { state: liveState({ data: z.object({ count: z.number() }) }) },
  }),
});

function stubSource(count: number): LiveSource {
  return {
    snapshot: () => ({ generation: 1, sequence: 0, timestamp: 0, data: { count } }),
    subscribe: vi.fn(() => vi.fn()),
  };
}

describe('forwardLiveModel', () => {
  it('passes the upstream live source through untouched', async () => {
    const source = stubSource(42);
    const resolveState = vi.fn(async () => source);
    const provider = forwardLiveModel(contract.state, resolveState);

    expect(provider.kind).toBe('liveModelProvider');
    expect(provider.contract).toBe(contract.state);
    // Identity pass-through: subscribers get the upstream source's own
    // snapshot-on-subscribe and update semantics, with nothing re-authored.
    await expect(provider.resolveState({ id: 'x' }, 'state')).resolves.toBe(source);
    expect(resolveState).toHaveBeenCalledWith({ id: 'x' }, 'state');
  });

  it('rejects mutations with the default message', async () => {
    const provider = forwardLiveModel(contract.state, async () => stubSource(1));

    await expect(provider.runMutation('anything' as never, {} as never)).rejects.toThrow(
      "Live model 'state' has no mutations"
    );
  });

  it('rejects mutations with a configured message', async () => {
    const provider = forwardLiveModel(contract.state, async () => stubSource(1), {
      mutationMessage: 'Use the tree mutations endpoint instead',
    });

    await expect(provider.runMutation('anything' as never, {} as never)).rejects.toThrow(
      'Use the tree mutations endpoint instead'
    );
  });
});
