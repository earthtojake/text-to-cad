import type { Unsubscribe } from '@emdash/shared';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { client } from '../rpc/client';
import { createController } from '../rpc/controller';
import { connect } from './connect';
import { defineContract, procedure } from './define';
import type { WireMessage, WireTransport } from './protocol';
import { serve } from './serve';
import { memoryTransportPair, reconnectingTransport } from './transports';

describe('connect', () => {
  it('disposes a logical connection without closing its transport', async () => {
    const transport = new TrackedTransport();
    const connection = connect(transport);
    const pending = connection.call('initialize', { protocolVersion: '1.0.0' });

    expect(transport.messageSubscriberCount).toBe(1);
    connection.dispose();

    await expect(pending).rejects.toMatchObject({
      code: 'DISCONNECTED',
      message: 'Wire connection disposed',
    });
    expect(transport.messageSubscriberCount).toBe(0);
    expect(transport.closed).toBe(false);
    await expect(connection.call('health', undefined)).rejects.toMatchObject({
      code: 'DISCONNECTED',
    });
  });

  it('can initialize every candidate before a stable connection uses it', async () => {
    const contract = defineContract({
      initialize: procedure({ input: z.string(), output: z.string() }),
      operation: procedure({ input: z.void().optional(), output: z.string() }),
    });
    const pairs: ReturnType<typeof memoryTransportPair>[] = [];
    const serverDisposers: Unsubscribe[] = [];
    const callOrder: string[][] = [];
    const transport = reconnectingTransport(async () => {
      const pair = memoryTransportPair();
      const generationCalls: string[] = [];
      const controller = createController(contract, {
        initialize: (version) => {
          generationCalls.push(`initialize:${version}`);
          return version;
        },
        operation: () => {
          generationCalls.push('operation');
          return 'ready';
        },
      });
      pairs.push(pair);
      callOrder.push(generationCalls);
      serverDisposers.push(serve(pair.right, controller));

      const handshakeConnection = connect(pair.left);
      try {
        await client(contract, handshakeConnection).initialize('1.0.0');
      } finally {
        handshakeConnection.dispose();
      }
      return pair.left;
    });
    const stableClient = client(contract, connect(transport));

    await transport.ready();
    await expect(stableClient.operation()).resolves.toBe('ready');
    expect(callOrder[0]).toEqual(['initialize:1.0.0', 'operation']);

    pairs[0]?.disconnect();
    await transport.ready();
    await expect(stableClient.operation()).resolves.toBe('ready');
    expect(callOrder[1]).toEqual(['initialize:1.0.0', 'operation']);

    transport.close();
    for (const dispose of serverDisposers) dispose();
  });
});

class TrackedTransport implements WireTransport {
  readonly sent: WireMessage[] = [];
  closed = false;
  private readonly messageListeners = new Set<(message: WireMessage) => void>();
  private readonly disconnectListeners = new Set<() => void>();

  get messageSubscriberCount(): number {
    return this.messageListeners.size;
  }

  post(message: WireMessage): void {
    if (this.closed) throw new Error('Tracked transport closed');
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

  close(): void {
    this.closed = true;
  }
}
