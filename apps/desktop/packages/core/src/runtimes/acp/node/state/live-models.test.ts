import { peek } from '@emdash/wire/state';
import { describe, expect, it } from 'vitest';
import {
  createAcpSessionLiveHost,
  createAcpSessionsLiveHost,
  createSessionLiveModels,
  produceCell,
} from './live-models';

describe('ACP live models', () => {
  it('executes cell producers once', async () => {
    const host = createAcpSessionsLiveHost();
    let calls = 0;

    produceCell(host.model.states.list, () => {
      calls += 1;
    });

    expect(calls).toBe(1);
    await host.dispose();
  });

  it("keeps a conversation's cells stable across dispose and restart", async () => {
    const host = createAcpSessionLiveHost();
    const initial = { lifecycle: 'starting', isGenerating: false } as never;
    const first = createSessionLiveModels(host, 'conv-1', initial);
    const activeTurn = first.states.activeTurn;
    activeTurn.set({ id: 'turn-1', status: 'active', items: [] } as never);
    first.states.usage.set({ contextSize: 10, usedTokens: 2 } as never);

    first.dispose();
    expect(host.models.get('conv-1')).toBe(first);

    const second = createSessionLiveModels(host, 'conv-1', initial);
    expect(second).toBe(first);
    expect(second.states.activeTurn).toBe(activeTurn);
    expect(peek(activeTurn)).toBeNull();
    expect(peek(second.states.usage)).toBeNull();
    expect(peek(second.states.state)).toEqual(initial);
    await host.dispose();
  });
});
