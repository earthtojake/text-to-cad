import { describe, expect, it } from 'vitest';
import type { ConnectionState, SshConnectionEvent } from '@core/primitives/ssh/api';
import { SshConnectionsModel } from './connections-model';

describe('SshConnectionsModel', () => {
  it('maps every manager event into one authoritative runtime record', () => {
    const model = new SshConnectionsModel();
    const stateEvents: Array<[SshConnectionEvent, ConnectionState]> = [
      [{ type: 'connecting', connectionId: 'connecting' }, 'connecting'],
      [{ type: 'connected', connectionId: 'connected' }, 'connected'],
      [
        { type: 'reconnecting', connectionId: 'reconnecting', attempt: 1, delayMs: 1_000 },
        'reconnecting',
      ],
      [{ type: 'reconnected', connectionId: 'reconnected' }, 'connected'],
      [{ type: 'disconnected', connectionId: 'disconnected' }, 'disconnected'],
      [{ type: 'reconnect-failed', connectionId: 'reconnect-failed' }, 'disconnected'],
      [{ type: 'error', connectionId: 'error', errorMessage: 'failed' }, 'error'],
    ];

    for (const [event] of stateEvents) model.publishEvent(event);

    const runtime = model.snapshot();
    for (const [event, state] of stateEvents) {
      expect(runtime[event.connectionId]).toEqual({
        state,
        health: { status: 'ok' },
      });
    }
    model.dispose();
  });

  it('merges health changes without losing state and retains healthy entries', () => {
    const model = new SshConnectionsModel();

    model.publishEvent({
      type: 'health-changed',
      connectionId: 'ssh-1',
      health: { status: 'degraded' },
    });
    expect(model.snapshot()['ssh-1']).toEqual({
      state: 'disconnected',
      health: { status: 'degraded' },
    });

    model.publishEvent({ type: 'connected', connectionId: 'ssh-1' });
    expect(model.snapshot()['ssh-1']).toEqual({
      state: 'connected',
      health: { status: 'degraded' },
    });

    model.publishEvent({
      type: 'health-changed',
      connectionId: 'ssh-1',
      health: { status: 'ok' },
    });
    expect(model.snapshot()['ssh-1']).toEqual({
      state: 'connected',
      health: { status: 'ok' },
    });
    model.dispose();
  });

  it('removes deleted connection runtime state', () => {
    const model = new SshConnectionsModel();
    model.publishEvent({ type: 'connected', connectionId: 'ssh-1' });

    model.remove('ssh-1');

    expect(model.snapshot()).toEqual({});
    model.dispose();
  });
});
