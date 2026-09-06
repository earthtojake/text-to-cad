import { describe, expect, it } from 'vitest';
import { createMemoryKeyValueStore } from '#primitives/kv/api';
import { createKvSessionIntentStore } from './store';

describe('createKvSessionIntentStore', () => {
  it('saves, lists, suspends, and removes intents within a scope', async () => {
    const store = createMemoryKeyValueStore();
    const acp = createKvSessionIntentStore(store, 'acp', { now: () => 1 });
    const tui = createKvSessionIntentStore(store, 'tui-agents', { now: () => 2 });

    await expect(
      acp.saveActive({
        conversationId: 'conv-1',
        payload: { conversationId: 'conv-1', cwd: '/repo' },
        sessionId: 'session-1',
      })
    ).resolves.toEqual({ success: true });
    await tui.saveActive({
      conversationId: 'conv-1',
      payload: { conversationId: 'conv-1', cwd: '/repo' },
    });

    await expect(acp.list()).resolves.toEqual({
      success: true,
      data: [
        {
          conversationId: 'conv-1',
          status: 'active',
          payload: { conversationId: 'conv-1', cwd: '/repo' },
          sessionId: 'session-1',
          updatedAt: 1,
        },
      ],
    });

    await acp.markSuspended('conv-1', 'idle');
    const suspended = await acp.list();

    expect(suspended.success ? suspended.data[0] : null).toMatchObject({
      conversationId: 'conv-1',
      status: 'suspended',
      suspendedCause: 'idle',
    });

    await acp.remove('conv-1');
    await expect(acp.list()).resolves.toEqual({ success: true, data: [] });
    await expect(tui.list()).resolves.toEqual({
      success: true,
      data: [
        {
          conversationId: 'conv-1',
          status: 'active',
          payload: { conversationId: 'conv-1', cwd: '/repo' },
          updatedAt: 2,
        },
      ],
    });
  });

  it('ignores malformed entries when listing', async () => {
    const store = createKvSessionIntentStore(
      createMemoryKeyValueStore({
        'session-intents:acp:bad': { status: 'active' },
        'session-intents:acp:good': {
          conversationId: 'good',
          status: 'active',
          payload: { conversationId: 'good' },
          updatedAt: 1,
        },
      }),
      'acp'
    );

    await expect(store.list()).resolves.toEqual({
      success: true,
      data: [
        {
          conversationId: 'good',
          status: 'active',
          payload: { conversationId: 'good' },
          updatedAt: 1,
        },
      ],
    });
  });
});
