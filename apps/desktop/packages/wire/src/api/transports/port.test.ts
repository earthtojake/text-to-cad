import { describe, expect, it, vi } from 'vitest';
import { portTransport, type PortLike } from './port';

describe('portTransport', () => {
  it('filters incoming messages and removes listeners on close', () => {
    const port = new FakePort();
    const transport = portTransport(port);
    const messages: unknown[] = [];
    const disconnected = vi.fn();

    transport.onMessage((message) => messages.push(message));
    transport.onDisconnect(disconnected);

    port.emit('message', { data: { kind: 'cancel', id: 'call-1' } });
    port.emit('message', { data: { kind: 'unknown' } });
    expect(messages).toEqual([{ kind: 'cancel', id: 'call-1' }]);

    transport.close?.();
    port.emit('message', { data: { kind: 'cancel', id: 'call-2' } });
    port.emit('close');

    expect(messages).toEqual([{ kind: 'cancel', id: 'call-1' }]);
    expect(disconnected).not.toHaveBeenCalled();
    expect(port.closeCalls).toBe(1);
  });

  it('notifies disconnect listeners on natural close', () => {
    const port = new FakePort();
    const transport = portTransport(port);
    const disconnected = vi.fn();

    transport.onDisconnect(disconnected);
    port.emit('close');

    expect(disconnected).toHaveBeenCalledTimes(1);
  });
});

class FakePort implements PortLike {
  closeCalls = 0;
  private readonly listeners = new Map<string, Set<(...args: unknown[]) => void>>();

  postMessage(): void {}

  on(event: string, cb: (...args: unknown[]) => void): void {
    this.listenersFor(event).add(cb);
  }

  off(event: string, cb: (...args: unknown[]) => void): void {
    this.listeners.get(event)?.delete(cb);
  }

  close(): void {
    this.closeCalls += 1;
  }

  emit(event: string, ...args: unknown[]): void {
    for (const listener of this.listeners.get(event) ?? []) listener(...args);
  }

  private listenersFor(event: string): Set<(...args: unknown[]) => void> {
    let listeners = this.listeners.get(event);
    if (!listeners) {
      listeners = new Set();
      this.listeners.set(event, listeners);
    }
    return listeners;
  }
}
