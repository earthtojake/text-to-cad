import { describe, expect, it } from 'vitest';
import type { WireMessage } from '../protocol';
import { domPortTransport } from './dom-port';

class FakeDomPort {
  posted: WireMessage[] = [];
  started = false;
  private listeners = new Map<string, Set<(event: { data?: unknown }) => void>>();

  postMessage(message: unknown): void {
    this.posted.push(message as WireMessage);
  }

  start(): void {
    this.started = true;
  }

  addEventListener(event: string, cb: (event: { data?: unknown }) => void): void {
    let listeners = this.listeners.get(event);
    if (!listeners) {
      listeners = new Set();
      this.listeners.set(event, listeners);
    }
    listeners.add(cb);
  }

  removeEventListener(event: string, cb: (event: { data?: unknown }) => void): void {
    this.listeners.get(event)?.delete(cb);
  }

  emit(event: string, data?: unknown): void {
    for (const cb of this.listeners.get(event) ?? []) cb({ data });
  }
}

describe('domPortTransport', () => {
  it('roundtrips messages and fires disconnects', () => {
    const port = new FakeDomPort();
    const transport = domPortTransport(port);
    const messages: WireMessage[] = [];
    let disconnected = false;
    transport.onMessage((message) => messages.push(message));
    transport.onDisconnect(() => {
      disconnected = true;
    });

    transport.post({ kind: 'detach', topic: 'topic' });
    port.emit('message', { kind: 'cancel', id: 'call-1' });
    port.emit('message', { kind: 'unknown' });
    port.emit('close');

    expect(port.started).toBe(true);
    expect(port.posted).toEqual([{ kind: 'detach', topic: 'topic' }]);
    expect(messages).toEqual([{ kind: 'cancel', id: 'call-1' }]);
    expect(disconnected).toBe(true);
  });
});
