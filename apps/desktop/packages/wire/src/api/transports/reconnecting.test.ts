import type { Unsubscribe } from '@emdash/shared';
import { deferred } from '@emdash/shared/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WireError, type WireMessage, type WireTransport } from '../protocol';
import { reconnectingTransport } from './reconnecting';

describe('reconnectingTransport', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('throws a DISCONNECTED WireError for posts before the first connection', async () => {
    const connected = deferred<WireTransport>();
    const transport = reconnectingTransport(() => connected.promise);
    const inner = new FakeTransport();

    expect(() => transport.post({ kind: 'detach', topic: 'early' })).toThrowError(WireError);

    connected.resolve(inner);
    await transport.ready();
    transport.post({ kind: 'detach', topic: 'after-ready' });
    expect(inner.sent).toEqual([{ kind: 'detach', topic: 'after-ready' }]);
    transport.close();
  });

  it('reaches readiness only after connectOnce completes', async () => {
    const handshake = deferred<void>();
    const inner = new FakeTransport();
    const transport = reconnectingTransport(async () => {
      await handshake.promise;
      return inner;
    });
    let ready = false;
    void transport.ready().then(() => {
      ready = true;
    });

    await Promise.resolve();
    expect(ready).toBe(false);

    handshake.resolve();
    await transport.ready();
    await vi.waitFor(() => expect(ready).toBe(true));
    transport.close();
  });

  it('fires reconnect on every established connection, including the first', async () => {
    const firstReady = deferred<WireTransport>();
    const secondReady = deferred<WireTransport>();
    const first = new FakeTransport();
    const second = new FakeTransport();
    const reconnects: string[] = [];
    const transport = reconnectingTransport(() =>
      firstReady.settled ? secondReady.promise : firstReady.promise
    );
    transport.onReconnect(() => reconnects.push('reconnected'));

    firstReady.resolve(first);
    await transport.ready();
    expect(reconnects).toEqual(['reconnected']);

    first.disconnect();
    secondReady.resolve(second);
    await vi.waitFor(() => expect(reconnects).toEqual(['reconnected', 'reconnected']));
    transport.close();
  });

  it('recovers from a failing inner post by reconnecting', async () => {
    const firstReady = deferred<WireTransport>();
    const secondReady = deferred<WireTransport>();
    const first = new FakeTransport();
    const second = new FakeTransport();
    first.failPostCount = 1;
    const disconnects: string[] = [];
    const transport = reconnectingTransport(() =>
      firstReady.settled ? secondReady.promise : firstReady.promise
    );
    transport.onDisconnect(() => disconnects.push('disconnected'));

    firstReady.resolve(first);
    await transport.ready();

    expect(() => transport.post({ kind: 'detach', topic: 'failing' })).toThrow(
      'Fake transport post failed'
    );
    expect(disconnects).toEqual(['disconnected']);

    secondReady.resolve(second);
    await transport.ready();
    transport.post({ kind: 'detach', topic: 'after-recovery' });
    expect(second.sent).toEqual([{ kind: 'detach', topic: 'after-recovery' }]);
    transport.close();
  });

  it('returns readiness for the replacement connection after disconnect', async () => {
    const firstReady = deferred<WireTransport>();
    const secondReady = deferred<WireTransport>();
    const first = new FakeTransport();
    const second = new FakeTransport();
    const transport = reconnectingTransport(() =>
      firstReady.settled ? secondReady.promise : firstReady.promise
    );

    firstReady.resolve(first);
    await transport.ready();
    first.disconnect();

    let replacementReady = false;
    void transport.ready().then(() => {
      replacementReady = true;
    });
    await Promise.resolve();
    expect(replacementReady).toBe(false);

    secondReady.resolve(second);
    await transport.ready();
    await vi.waitFor(() => expect(replacementReady).toBe(true));
    transport.close();
  });

  it('stops retrying and rejects readiness for a permanent initial failure', async () => {
    const mismatch = new Error('protocol mismatch');
    const terminalFailures: unknown[] = [];
    let attempts = 0;
    const transport = reconnectingTransport(
      () => {
        attempts += 1;
        return Promise.reject(mismatch);
      },
      { shouldRetry: () => false }
    );
    transport.onTerminalFailure((error) => terminalFailures.push(error));

    await expect(transport.ready()).rejects.toBe(mismatch);
    expect(attempts).toBe(1);
    expect(terminalFailures).toEqual([mismatch]);

    // Down-path posts surface a WireError carrying the terminal cause, never
    // the raw terminal error.
    try {
      transport.post({ kind: 'detach', topic: 'rejected' });
      expect.unreachable('post after terminal failure must throw');
    } catch (error) {
      expect(error).toBeInstanceOf(WireError);
      expect((error as WireError).code).toBe('DISCONNECTED');
      expect((error as WireError).cause).toBe(mismatch);
    }
    transport.close();
  });

  it('notifies late terminal-failure subscribers immediately', async () => {
    const mismatch = new Error('protocol mismatch');
    const transport = reconnectingTransport(() => Promise.reject(mismatch), {
      shouldRetry: () => false,
    });

    await expect(transport.ready()).rejects.toBe(mismatch);
    const terminalFailures: unknown[] = [];
    transport.onTerminalFailure((error) => terminalFailures.push(error));
    expect(terminalFailures).toEqual([mismatch]);
    transport.close();
  });

  it('rejects readiness when retry classification fails', async () => {
    const classificationError = new Error('classification failed');
    const transport = reconnectingTransport(() => Promise.reject(new Error('offline')), {
      shouldRetry: () => {
        throw classificationError;
      },
    });

    await expect(transport.ready()).rejects.toBe(classificationError);
    transport.close();
  });

  it('rejects replacement readiness after a permanent failure', async () => {
    const first = new FakeTransport();
    const mismatch = new Error('protocol mismatch');
    const reconnects: string[] = [];
    const failures: Array<{ attempt: number; isReconnect: boolean }> = [];
    let attempts = 0;
    const transport = reconnectingTransport(
      () => {
        attempts += 1;
        return attempts === 1 ? Promise.resolve(first) : Promise.reject(mismatch);
      },
      {
        shouldRetry: (_error, context) => {
          failures.push(context);
          return false;
        },
      }
    );
    transport.onReconnect(() => reconnects.push('reconnected'));

    await transport.ready();
    expect(reconnects).toEqual(['reconnected']);
    first.disconnect();

    await expect(transport.ready()).rejects.toBe(mismatch);
    expect(attempts).toBe(2);
    expect(failures).toEqual([{ attempt: 0, isReconnect: true }]);
    expect(reconnects).toEqual(['reconnected']);
    transport.close();
  });

  it('caps reconnect backoff at the last configured delay', async () => {
    vi.useFakeTimers();
    let attempts = 0;
    const transport = reconnectingTransport(
      () => {
        attempts += 1;
        return Promise.reject(new Error('offline'));
      },
      { backoffMs: [10, 20] }
    );

    await Promise.resolve();
    await Promise.resolve();
    expect(attempts).toBe(1);

    await vi.advanceTimersByTimeAsync(10);
    expect(attempts).toBe(2);
    await vi.advanceTimersByTimeAsync(20);
    expect(attempts).toBe(3);
    await vi.advanceTimersByTimeAsync(20);
    expect(attempts).toBe(4);

    transport.close();
  });

  it('stops retrying when closed', async () => {
    vi.useFakeTimers();
    let attempts = 0;
    const transport = reconnectingTransport(
      () => {
        attempts += 1;
        return Promise.reject(new Error('offline'));
      },
      { backoffMs: [10] }
    );

    await Promise.resolve();
    await Promise.resolve();
    expect(attempts).toBe(1);

    transport.close();
    await vi.advanceTimersByTimeAsync(100);
    expect(attempts).toBe(1);
  });

  it('reports a terminal failure when closed', async () => {
    const connected = deferred<WireTransport>();
    const transport = reconnectingTransport(() => connected.promise);
    const inner = new FakeTransport();
    connected.resolve(inner);
    await transport.ready();

    const terminalFailures: unknown[] = [];
    transport.onTerminalFailure((error) => terminalFailures.push(error));
    transport.close();

    expect(terminalFailures).toHaveLength(1);
    expect(terminalFailures[0]).toBeInstanceOf(Error);
  });
});

class FakeTransport implements WireTransport {
  readonly sent: WireMessage[] = [];
  failPostCount = 0;
  private readonly messageListeners = new Set<(message: WireMessage) => void>();
  private readonly disconnectListeners = new Set<() => void>();
  private closed = false;

  get disconnectSubscriberCount(): number {
    return this.disconnectListeners.size;
  }

  post(message: WireMessage): void {
    if (this.closed) throw new Error('Fake transport closed');
    if (this.failPostCount > 0) {
      this.failPostCount -= 1;
      throw new Error('Fake transport post failed');
    }
    this.sent.push(message);
  }

  onMessage(cb: (message: WireMessage) => void): Unsubscribe {
    this.messageListeners.add(cb);
    return () => this.messageListeners.delete(cb);
  }

  onDisconnect(cb: () => void): Unsubscribe {
    this.disconnectListeners.add(cb);
    return () => this.disconnectListeners.delete(cb);
  }

  disconnect(): void {
    if (this.closed) return;
    this.closed = true;
    for (const listener of this.disconnectListeners) listener();
  }

  close(): void {
    this.disconnect();
    this.messageListeners.clear();
    this.disconnectListeners.clear();
  }
}
