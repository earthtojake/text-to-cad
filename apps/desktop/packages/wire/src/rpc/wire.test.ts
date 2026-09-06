import { err, ok, type Unsubscribe } from '@emdash/shared';
import { deferred, waitFor } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import type { LiveSource, LiveUpdate } from '../api/channel';
import { connect } from '../api/connect';
import { defineContract, liveModel, liveState, fallible, procedure } from '../api/define';
import { isWireError, WireError, type WireMessage, type WireTransport } from '../api/protocol';
import { serve } from '../api/serve';
import { encodeTopic } from '../api/topics';
import { memoryTransportPair, reconnectingTransport } from '../api/transports';
import { ReplicaState } from '../live/replica';
import { LiveStateSource } from '../live/state/source';
import { createTestWire } from '../testing';
import { client } from './client';
import { createController } from './controller';

const contract = defineContract({
  greet: procedure({ input: z.object({ name: z.string() }), output: z.string() }),
  fail: procedure({ input: z.void().optional(), output: z.void() }),
  state: liveModel({
    key: z.object({ id: z.string() }),
    states: { state: liveState({ data: z.object({ count: z.number() }) }) },
  }),
});

function knownStateProvider(model: LiveStateSource<{ count: number }>) {
  return {
    kind: 'liveModelProvider' as const,
    contract: contract.state,
    resolveState: (key: { id: string }) => (key.id === 'known' ? model : undefined),
    runMutation: async (): Promise<never> => {
      throw new WireError('UNKNOWN_PROCEDURE', 'no mutations');
    },
  };
}

function setup() {
  const model = new LiveStateSource({ count: 0 });
  const wire = createTestWire(contract, {
    greet: ({ name }) => `hello ${name}`,
    fail: () => {
      throw new WireError('NOT_FOUND', 'expected failure');
    },
    state: knownStateProvider(model),
  });
  return { pair: wire.pair, connection: wire.connection, model };
}

function structuredCloneTransport(transport: WireTransport): WireTransport {
  return {
    ...transport,
    post(message) {
      transport.post(structuredClone(message));
    },
  };
}

describe('wire serve/connect', () => {
  it('calls procedures and propagates errors', async () => {
    const { connection } = setup();
    await expect(connection.call('greet', { name: 'wire' })).resolves.toBe('hello wire');
    await expect(connection.call('fail', undefined)).rejects.toMatchObject({ code: 'NOT_FOUND' });
  });

  it('round-trips uncaught handler errors as HANDLER_ERROR with a serialized cause', async () => {
    const failingContract = defineContract({
      fail: procedure({ input: z.void().optional(), output: z.void() }),
    });
    const { connection } = createTestWire(failingContract, {
      fail: () => {
        throw new TypeError('boom');
      },
    });

    await expect(connection.call('fail', undefined)).rejects.toMatchObject({
      code: 'HANDLER_ERROR',
      message: 'boom',
      cause: {
        name: 'TypeError',
        message: 'boom',
      },
    });
  });

  it('reports non-cloneable call inputs as SERIALIZATION errors with a value path', async () => {
    const pair = memoryTransportPair();
    const connection = connect(structuredCloneTransport(pair.left));
    const labelNames = new Proxy(['bug'], {});

    await expect(
      connection.call('pullRequests.listPullRequests', {
        filters: { labelNames },
      })
    ).rejects.toMatchObject({
      code: 'SERIALIZATION',
      message:
        "Wire call 'pullRequests.listPullRequests' could not be serialized: " +
        "'input.filters.labelNames' is an Array value that cannot be structured-cloned " +
        '(it may be Proxy-backed)',
    });
  });

  it('reports non-cloneable handler results as SERIALIZATION errors with a value path', async () => {
    const pair = memoryTransportPair();
    const output = { filters: { labelNames: new Proxy(['bug'], {}) } };
    serve(structuredCloneTransport(pair.right), {
      call: async () => output,
      resolveLive: () => null,
      acquireLive: () => null,
    });
    const connection = connect(pair.left);

    await expect(connection.call('pullRequests.listPullRequests', undefined)).rejects.toMatchObject(
      {
        code: 'SERIALIZATION',
        message:
          "Wire response for call 'pullRequests.listPullRequests' could not be serialized: " +
          "'value.filters.labelNames' is an Array value that cannot be structured-cloned " +
          '(it may be Proxy-backed)',
      }
    );
  });

  it('preserves serialized causes on thrown wire errors', async () => {
    const failingContract = defineContract({
      fail: procedure({ input: z.void().optional(), output: z.void() }),
    });
    const cause = new Error('root cause');
    const { connection } = createTestWire(failingContract, {
      fail: () => {
        throw new WireError('NOT_FOUND', 'missing resource', { cause });
      },
    });

    await expect(connection.call('fail', undefined)).rejects.toMatchObject({
      code: 'NOT_FOUND',
      message: 'missing resource',
      cause: {
        name: 'Error',
        message: 'root cause',
      },
    });
  });

  it('narrows wire errors with and without a code argument', () => {
    const error: unknown = new WireError('CANCELLED', 'cancelled');

    expect(isWireError(error)).toBe(true);
    expect(isWireError(error, 'CANCELLED')).toBe(true);
    expect(isWireError(error, 'DISCONNECTED')).toBe(false);
    expect(isWireError(new Error('plain'))).toBe(false);
  });

  it('supports fallible procedures that return typed Result payloads', async () => {
    const fallibleContract = defineContract({
      load: fallible({
        input: z.object({ id: z.string() }),
        data: z.object({ value: z.string() }),
        error: z.object({ type: z.literal('missing') }),
      }),
    });
    const { connection } = createTestWire(
      fallibleContract,
      {
        load: ({ id }) =>
          id === 'known' ? ok({ value: 'found' }) : err({ type: 'missing' as const }),
      },
      { validate: 'full' }
    );

    await expect(connection.call('load', { id: 'known' })).resolves.toEqual(ok({ value: 'found' }));
    await expect(connection.call('load', { id: 'missing' })).resolves.toEqual(
      err({ type: 'missing' })
    );
    expect(fallibleContract.load.output.safeParse({ success: true }).success).toBe(false);
  });

  it('supports no-data fallible procedures across JSON transports', () => {
    const fallibleContract = defineContract({
      touch: fallible({
        input: z.object({ id: z.string() }),
        error: z.object({ type: z.literal('missing') }),
      }),
    });
    const jsonRoundTrippedSuccess = JSON.parse(JSON.stringify(ok())) as unknown;

    expect(jsonRoundTrippedSuccess).toEqual({ success: true });
    expect(fallibleContract.touch.output.parse(jsonRoundTrippedSuccess)).toEqual(ok());
    expect(fallibleContract.touch.output.parse(err({ type: 'missing' as const }))).toEqual(
      err({ type: 'missing' })
    );
  });

  it('supports explicit data: z.void() fallible procedures across JSON transports', () => {
    const fallibleContract = defineContract({
      touch: fallible({
        input: z.object({ id: z.string() }),
        data: z.void(),
        error: z.object({ type: z.literal('missing') }),
      }),
    });
    const jsonRoundTrippedSuccess = JSON.parse(JSON.stringify(ok())) as unknown;

    expect(jsonRoundTrippedSuccess).toEqual({ success: true });
    expect(fallibleContract.touch.output.parse(jsonRoundTrippedSuccess)).toEqual(ok());
    expect(fallibleContract.touch.output.parse(err({ type: 'missing' as const }))).toEqual(
      err({ type: 'missing' })
    );
  });

  it('snapshots and subscribes to live sources with refcounted detach', async () => {
    const { connection, model } = setup();
    const topic = encodeTopic(contract.state.states.state.id, { id: 'known' });
    await expect(connection.snapshot(topic)).resolves.toMatchObject({ data: { count: 0 } });

    const updates: LiveUpdate[] = [];
    const detach = await connection.attach(topic, (update) => updates.push(update));
    model.produce((draft) => {
      draft.count = 1;
    });
    await waitFor(() => updates.length === 1);
    detach();
    model.produce((draft) => {
      draft.count = 2;
    });
    await Promise.resolve();
    expect(updates).toHaveLength(1);
  });

  it('surfaces attach failures for unknown topics', async () => {
    const { connection } = setup();
    await expect(connection.attach('missing.topic', () => {})).rejects.toMatchObject({
      code: 'UNKNOWN_TOPIC',
    });
  });

  it('removes failed attachment entries so later attaches can retry the topic', async () => {
    const pair = memoryTransportPair();
    let available = false;
    let resolveCount = 0;
    const source: LiveSource = {
      snapshot: () => ({ generation: 1, sequence: 0, timestamp: 0, data: {} }),
      subscribe: () => () => {},
    };
    const controller = {
      call: () => {
        throw new WireError('UNKNOWN_PROCEDURE', 'not implemented');
      },
      resolveLive: (topic: string) => {
        resolveCount += 1;
        return available && topic === 'dynamic.topic' ? source : null;
      },
      acquireLive(topic: string) {
        const resolved = this.resolveLive(topic);
        if (!resolved) return null;
        return {
          ready: async () => resolved,
          release: async () => {},
        };
      },
    };
    serve(pair.right, controller);
    const connection = connect(pair.left);

    await expect(connection.attach('dynamic.topic', () => {})).rejects.toMatchObject({
      code: 'UNKNOWN_TOPIC',
    });

    available = true;
    const detach = await connection.attach('dynamic.topic', () => {});
    expect(resolveCount).toBe(2);
    detach();
  });

  it('reports retryable reattach failures and keeps the attachment durable', async () => {
    const transport = new ControlledTransport();
    const connection = connect(transport);
    const updates: LiveUpdate[] = [];
    const gaps: string[] = [];
    const errors: Array<{ code: string; retrying: boolean }> = [];

    const attached = connection.attach('live.topic', (update) => updates.push(update), {
      onReattach: () => gaps.push('gap'),
      onReattachError: (error, context) =>
        errors.push({ code: error.code, retrying: context.retrying }),
    });
    transport.resolveAttach('live.topic');
    const detach = await attached;

    transport.reconnect();
    transport.rejectAttach('live.topic', 'DISCONNECTED');
    await waitFor(() => errors.length === 1);

    transport.reconnect();
    transport.resolveAttach('live.topic');
    await waitFor(() => gaps.length === 1);
    transport.emit({
      kind: 'update',
      topic: 'live.topic',
      update: {
        generation: 1,
        baseSequence: 0,
        sequence: 1,
        timestamp: 0,
        delta: {},
      },
    });

    expect(errors).toEqual([{ code: 'DISCONNECTED', retrying: true }]);
    expect(updates).toHaveLength(1);
    detach();
    expect(transport.sent).toContainEqual({ kind: 'detach', topic: 'live.topic' });
  });

  it('terminates attachments on non-retryable reattach failures', async () => {
    const transport = new ControlledTransport();
    const connection = connect(transport);
    const updates: LiveUpdate[] = [];
    const errors: Array<{ code: string; retrying: boolean }> = [];

    const attached = connection.attach('live.topic', (update) => updates.push(update), {
      onReattachError: (error, context) =>
        errors.push({ code: error.code, retrying: context.retrying }),
    });
    transport.resolveAttach('live.topic');
    const detach = await attached;

    transport.reconnect();
    transport.rejectAttach('live.topic', 'UNKNOWN_TOPIC');
    await waitFor(() => errors.length === 1);
    transport.emit({
      kind: 'update',
      topic: 'live.topic',
      update: {
        generation: 1,
        baseSequence: 0,
        sequence: 1,
        timestamp: 0,
        delta: {},
      },
    });
    detach();

    expect(errors).toEqual([{ code: 'UNKNOWN_TOPIC', retrying: false }]);
    expect(updates).toEqual([]);
    expect(transport.sent).not.toContainEqual({ kind: 'detach', topic: 'live.topic' });
  });

  it('ignores stale reattach failures from older attempts', async () => {
    const transport = new ControlledTransport();
    const connection = connect(transport);
    const updates: LiveUpdate[] = [];
    const gaps: string[] = [];
    const errors: Array<{ code: string; retrying: boolean }> = [];

    const attached = connection.attach('live.topic', (update) => updates.push(update), {
      onReattach: () => gaps.push('gap'),
      onReattachError: (error, context) =>
        errors.push({ code: error.code, retrying: context.retrying }),
    });
    transport.resolveAttach('live.topic');
    const detach = await attached;

    transport.reconnect();
    const staleAttachId = transport.latestAttachId('live.topic');
    transport.reconnect();
    transport.rejectAttach('live.topic', 'UNKNOWN_TOPIC', staleAttachId);
    transport.resolveAttach('live.topic');
    await waitFor(() => gaps.length === 1);
    transport.emit({
      kind: 'update',
      topic: 'live.topic',
      update: {
        generation: 1,
        baseSequence: 0,
        sequence: 1,
        timestamp: 0,
        delta: {},
      },
    });

    expect(errors).toEqual([]);
    expect(updates).toHaveLength(1);
    detach();
  });

  it('cleans server subscriptions on disconnect', async () => {
    let detachCount = 0;
    const source: LiveSource = {
      snapshot: () => ({ generation: 1, sequence: 0, timestamp: 0, data: {} }),
      subscribe: () => {
        return () => {
          detachCount += 1;
        };
      },
    };
    const pair = memoryTransportPair();
    const cleanupContract = defineContract({
      state: liveModel({
        key: z.void().optional(),
        states: { state: liveState({ data: z.object({}) }) },
      }),
    });
    const controller = createController(cleanupContract, {
      state: {
        kind: 'liveModelProvider',
        contract: cleanupContract.state,
        resolveState: () => source,
        runMutation: async () => ok({ data: undefined, cursors: [] }),
      },
    });
    serve(pair.right, controller);
    const connection = connect(pair.left);
    await connection.attach(
      encodeTopic(cleanupContract.state.states.state.id, undefined),
      () => {}
    );
    pair.disconnect();
    expect(detachCount).toBe(1);
  });

  it('does not throw when an attachment is detached after disconnect', async () => {
    const { connection, pair, model } = setup();
    const topic = encodeTopic(contract.state.states.state.id, { id: 'known' });
    const updates: LiveUpdate[] = [];
    const detach = await connection.attach(topic, (update) => updates.push(update));
    pair.left.disconnect();
    await expect(connection.call('greet', { name: 'after' })).rejects.toMatchObject({
      code: 'DISCONNECTED',
    });
    expect(() => {
      model.produce((draft) => {
        draft.count = 1;
      });
    }).not.toThrow();
    expect(() => detach()).not.toThrow();
  });

  it('reattaches and refreshes bound live models after reconnect', async () => {
    const model = new LiveStateSource({ count: 0 });
    const controller = createController(contract, {
      greet: ({ name }) => `hello ${name}`,
      fail: () => {
        throw new WireError('NOT_FOUND', 'expected failure');
      },
      state: knownStateProvider(model),
    });
    const pairs: ReturnType<typeof memoryTransportPair>[] = [];
    const serverDisposers: Unsubscribe[] = [];
    const transport = reconnectingTransport(async () => {
      const pair = memoryTransportPair();
      pairs.push(pair);
      serverDisposers.push(serve(pair.right, controller));
      return pair.left;
    });
    const contractClient = client(contract, connect(transport));
    const seen: Array<{ count: number }> = [];
    const binding = new ReplicaState(contractClient.state.state({ id: 'known' }, 'state'), {
      schema: z.object({ count: z.number() }),
      onChange: (value) => seen.push(value),
    });

    await binding.ready;
    model.produce((draft) => {
      draft.count = 1;
    });
    await waitFor(() => binding.current().count === 1);

    pairs[0]?.disconnect();
    model.reseed({ count: 9 });

    await waitFor(() => pairs.length === 2);
    await waitFor(() => binding.current().count === 9);
    expect(seen.at(-1)).toEqual({ count: 9 });

    await binding.dispose();
    transport.close();
    for (const dispose of serverDisposers) dispose();
  });

  it('cancels an in-flight call with a caller signal', async () => {
    let aborted = false;
    let started = false;
    const pair = memoryTransportPair();
    const slowContract = defineContract({
      slow: procedure({ input: z.void().optional(), output: z.string() }),
    });
    const controller = createController(slowContract, {
      slow: (_input, meta) =>
        new Promise<string>((_resolve, reject) => {
          started = true;
          if (meta.signal?.aborted) {
            aborted = true;
            reject(new Error('aborted'));
            return;
          }
          meta.signal?.addEventListener('abort', () => {
            aborted = true;
            reject(new Error('aborted'));
          });
        }),
    });
    const serverEvents: unknown[] = [];
    serve(pair.right, controller, {
      instrumentation: {
        cancel: (event) => serverEvents.push({ kind: 'cancel', event }),
        callEnd: (event) => serverEvents.push({ kind: 'callEnd', event }),
      },
    });
    const connection = connect(pair.left);
    const abort = new AbortController();

    const result = connection.call('slow', undefined, { signal: abort.signal });
    await waitFor(() => started);
    abort.abort();

    await expect(result).rejects.toMatchObject({ code: 'CANCELLED' });
    await waitFor(() => aborted);
    expect(serverEvents).toContainEqual({
      kind: 'cancel',
      event: expect.objectContaining({ callId: expect.any(String), side: 'server' }),
    });
    expect(serverEvents).toContainEqual({
      kind: 'callEnd',
      event: expect.objectContaining({
        ok: false,
        errorCode: 'CANCELLED',
        side: 'server',
      }),
    });
  });

  it('rejects pre-aborted calls without posting', async () => {
    const { connection } = setup();
    const abort = new AbortController();
    abort.abort();

    await expect(
      connection.call('greet', { name: 'wire' }, { signal: abort.signal })
    ).rejects.toMatchObject({
      code: 'CANCELLED',
    });
  });

  it('aborts in-flight calls when the transport disconnects', async () => {
    let aborted = false;
    let started = false;
    const pair = memoryTransportPair();
    const slowContract = defineContract({
      slow: procedure({ input: z.void().optional(), output: z.string() }),
    });
    const controller = createController(slowContract, {
      slow: (_input, meta) =>
        new Promise<string>((_resolve, reject) => {
          started = true;
          if (meta.signal?.aborted) {
            aborted = true;
            reject(new Error('aborted'));
            return;
          }
          meta.signal?.addEventListener('abort', () => {
            aborted = true;
            reject(new Error('aborted'));
          });
        }),
    });
    serve(pair.right, controller);
    const connection = connect(pair.left);

    const result = connection.call('slow', undefined);
    await waitFor(() => started);
    pair.disconnect();

    await expect(result).rejects.toMatchObject({ code: 'DISCONNECTED' });
    await waitFor(() => aborted);
  });

  it('ignores a late result after local cancellation', async () => {
    const gate = deferred<string>();
    const pair = memoryTransportPair();
    const slowContract = defineContract({
      slow: procedure({ input: z.void().optional(), output: z.string() }),
    });
    const controller = createController(slowContract, { slow: () => gate.promise });
    serve(pair.right, controller);
    const connection = connect(pair.left);
    const abort = new AbortController();

    const result = connection.call('slow', undefined, { signal: abort.signal });
    abort.abort();

    await expect(result).rejects.toMatchObject({ code: 'CANCELLED' });
    gate.resolve('late');
    await Promise.resolve();
  });
});

class ControlledTransport implements WireTransport {
  readonly sent: WireMessage[] = [];
  private readonly messageListeners = new Set<(message: WireMessage) => void>();
  private readonly disconnectListeners = new Set<() => void>();
  private readonly reconnectListeners = new Set<() => void>();

  post(message: WireMessage): void {
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

  onReconnect(cb: () => void): Unsubscribe {
    this.reconnectListeners.add(cb);
    return () => this.reconnectListeners.delete(cb);
  }

  emit(message: WireMessage): void {
    for (const listener of this.messageListeners) listener(message);
  }

  reconnect(): void {
    for (const listener of this.reconnectListeners) listener();
  }

  resolveAttach(topic: string): void {
    this.emit({ kind: 'result', id: this.latestAttachId(topic), ok: true, value: undefined });
  }

  rejectAttach(topic: string, code: WireError['code'], id = this.latestAttachId(topic)): void {
    this.emit({ kind: 'result', id, ok: false, code, message: `${code} ${topic}` });
  }

  latestAttachId(topic: string): string {
    for (let index = this.sent.length - 1; index >= 0; index -= 1) {
      const message = this.sent[index];
      if (message.kind === 'attach' && message.topic === topic) return message.id;
    }
    throw new Error(`No attach message sent for ${topic}`);
  }
}
