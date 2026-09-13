import type { Unsubscribe } from '@emdash/shared';
import { waitFor } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { connect } from '../api/connect';
import { defineContract, eventStream, resourcedStream } from '../api/define';
import type { WireError } from '../api/protocol';
import { serve } from '../api/serve';
import { encodeTopic } from '../api/topics';
import { memoryTransportPair, reconnectingTransport } from '../api/transports';
import { createEventStreamHost, EventStreamSource } from '../live/event-stream';
import { createTestWire } from '../testing';
import { client } from './client';
import { createController } from './controller';

const contract = defineContract({
  events: eventStream({
    key: z.object({ id: z.string().trim() }),
    event: z.object({ message: z.string() }),
  }),
});

describe('eventStream API', () => {
  it('delivers events while attached and drops events emitted before attachment', async () => {
    const key = { id: 'known' };
    const host = createEventStreamHost(contract.events);
    const wire = createTestWire(contract, { events: host }, { validate: 'full' });
    const seen: Array<{ message: string }> = [];

    host.emit(key, { message: 'early' });
    const unsubscribe = await wire.client.events.subscribe(key, {
      onEvent: (event) => seen.push(event),
    });
    await waitFor(() => host.resolve(key).subscriberCount === 1);
    host.emit(key, { message: 'late' });
    await waitFor(() => seen.length === 1);

    try {
      expect(seen).toEqual([{ message: 'late' }]);
    } finally {
      unsubscribe();
      wire.dispose();
      host.dispose();
    }
  });

  it('signals a gap when an event stream reattaches after reconnect', async () => {
    const key = { id: 'known' };
    const host = createEventStreamHost(contract.events);
    const controller = createController(contract, { events: host });
    const pairs: ReturnType<typeof memoryTransportPair>[] = [];
    const serverDisposers: Unsubscribe[] = [];
    const transport = reconnectingTransport(async () => {
      const pair = memoryTransportPair();
      pairs.push(pair);
      serverDisposers.push(serve(pair.right, controller));
      return pair.left;
    });
    const contractClient = client(contract, connect(transport));
    const gaps: string[] = [];
    const seen: Array<{ message: string }> = [];
    const unsubscribe = await contractClient.events.subscribe(key, {
      onEvent: (event) => seen.push(event),
      onGap: () => gaps.push('gap'),
    });

    await waitFor(() => host.resolve(key).subscriberCount === 1);
    host.emit(key, { message: 'first' });
    await waitFor(() => seen.length === 1);
    expect(gaps).toEqual([]);

    pairs[0]?.disconnect();
    host.emit(key, { message: 'dropped' });
    await waitFor(() => pairs.length === 2);
    await waitFor(() => gaps.length === 1);
    await waitFor(() => host.resolve(key).subscriberCount === 1);
    host.emit(key, { message: 'second' });
    await waitFor(() => seen.length === 2);

    expect(seen).toEqual([{ message: 'first' }, { message: 'second' }]);
    unsubscribe();
    transport.close();
    for (const dispose of serverDisposers) dispose();
  });

  it('validates event stream keys before resolving topics', () => {
    const host = createEventStreamHost(contract.events);
    const wire = createTestWire(contract, { events: host }, { validate: 'inputs' });

    try {
      expect(() =>
        wire.controller.resolveLive(encodeTopic(contract.events.id, { id: 1 }))
      ).toThrow();
      expect(
        wire.controller.resolveLive(encodeTopic(contract.events.id, { id: ' known ' }))
      ).not.toBeNull();
    } finally {
      wire.dispose();
      host.dispose();
    }
  });

  it('rejects a bare resolver for a resourced event stream at bind time', () => {
    const resourcedContract = defineContract({
      events: resourcedStream({
        key: z.object({ id: z.string() }),
        event: z.object({ message: z.string() }),
      }),
    });

    expect(() =>
      createController(resourcedContract, {
        events: (() => new EventStreamSource()) as never,
      })
    ).toThrowError(expect.objectContaining<Partial<WireError>>({ code: 'CONTRACT_MISMATCH' }));
  });
});
