import { createScope } from '@emdash/shared/concurrency';
import { cell, flushStateTurn } from '@emdash/wire/state';
import { reaction } from 'mobx';
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import {
  AcpLiveSession,
  isTransientStartupError,
  remoteValueState,
  shouldRetryAcpStart,
} from './acp-live-session';

describe('remoteValueState', () => {
  it('invalidates MobX reactions when the Wire state changes', async () => {
    const source = cell<number | undefined>(1);
    const scope = createScope({ label: 'remote-value-state-test' });
    const state = remoteValueState(source, z.number(), scope);
    await state.ready;

    const seen: number[] = [];
    const dispose = reaction(
      () => state.current(),
      (value) => seen.push(value),
      {
        fireImmediately: true,
      }
    );

    source.set(2);
    flushStateTurn();

    expect(seen).toEqual([1, 2]);

    dispose();
    await scope.dispose();
  });
});

describe('AcpLiveSession.sendPrompt', () => {
  it('disables the Wire deadline for the turn-long prompt call', async () => {
    const sendPrompt = vi.fn(async () => ({ success: true, data: { queued: false } }));
    const session = Object.assign(Object.create(AcpLiveSession.prototype), {
      conversationId: 'conversation-1',
      client: { sendPrompt },
    }) as AcpLiveSession;

    await session.sendPrompt({ text: 'hello' });

    expect(sendPrompt).toHaveBeenCalledWith(
      {
        conversationId: 'conversation-1',
        prompt: { text: 'hello' },
        placement: undefined,
      },
      { timeoutMs: 0 }
    );
  });
});

describe('ACP startup retry classification', () => {
  it.each(['ETIMEDOUT', 'ECONNREFUSED'])('recognizes structured %s transport errors', (code) => {
    const error = Object.assign(new Error('provider startup failed'), { code });

    expect(isTransientStartupError(error)).toBe(true);
  });

  it('retries a transient new_session_failed result', () => {
    expect(
      shouldRetryAcpStart({
        kind: 'value',
        value: {
          success: false,
          error: {
            type: 'new_session_failed',
            cause: { name: 'Error', message: 'connect ECONNREFUSED 127.0.0.1' },
          },
        } as never,
      })
    ).toBe(true);
  });

  it('does not retry non-transient provider failures', () => {
    expect(
      shouldRetryAcpStart({
        kind: 'value',
        value: {
          success: false,
          error: {
            type: 'new_session_failed',
            cause: { name: 'Error', message: 'invalid provider configuration' },
          },
        } as never,
      })
    ).toBe(false);
  });
});
