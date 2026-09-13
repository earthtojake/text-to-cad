import { ok, type Unsubscribe } from '@emdash/shared';
import { waitFor } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import type { LiveSource, LiveSubscribeOptions, LiveUpdate } from '../api/channel';
import {
  defineContract,
  downloadFile,
  eventStream,
  liveJob,
  liveLog,
  liveModel,
  liveState,
  mutation,
  uploadFile,
} from '../api/define';
import { WireError } from '../api/protocol';
import { createEventStreamHost } from '../live/event-stream';
import { expose } from '../state/bridge/expose';
import { cell } from '../state/core';
import { createTestWire } from '../testing';
import { forwardContractImpl, forwardController } from './forward';

const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();
const errorSchema = z.object({ type: z.string() });

const contract = defineContract({
  download: downloadFile({
    input: z.object({ id: z.string() }),
    error: errorSchema,
  }),
  upload: uploadFile({
    input: z.object({ id: z.string() }),
    result: z.object({ id: z.string(), text: z.string() }),
    error: errorSchema,
  }),
  output: liveLog({
    key: z.object({ id: z.string() }),
  }),
  events: eventStream({
    key: z.object({ id: z.string() }),
    event: z.object({ message: z.string() }),
  }),
  task: liveJob({
    input: z.object({ name: z.string() }),
    progress: z.object({ step: z.string() }),
    result: z.object({ artifact: z.string() }),
    error: errorSchema,
  }),
  model: liveModel({
    key: z.object({ id: z.string() }),
    states: {
      state: liveState({ data: z.object({ count: z.number() }) }),
    },
    mutations: {
      bump: mutation({
        input: z.object({ amount: z.number() }),
        data: z.object({ count: z.number() }),
        error: errorSchema,
      }),
    },
  }),
});

function counterModelProvider(initial: { count: number }) {
  const state = cell(initial);
  return expose(
    contract.model,
    { state: () => state },
    {
      mutations: {
        async bump(context) {
          let count = 0;
          const revision = state.update(
            (previous) => {
              count = previous.count + context.input.amount;
              return { count };
            },
            { mutationIds: [context.mutationId] }
          );
          await context.observed('state', revision);
          return ok({ count });
        },
      },
    }
  );
}

describe('forwardController', () => {
  it('forwards every endpoint kind through an existing client', async () => {
    const key = { id: 'known' };
    const model = counterModelProvider({ count: 1 });
    const log = createLogSource('forwarded log');
    const events = createEventStreamHost(contract.events);
    const upstream = createTestWire(
      contract,
      {
        download: ({ id }) =>
          ok({
            meta: { name: `${id}.txt`, mimeType: 'text/plain', size: 11 },
            source: chunks(textEncoder.encode('hello world')),
          }),
        upload: async ({ id }, file) => ok({ id, text: textDecoder.decode(await file.bytes()) }),
        output: () => log,
        events,
        task: {
          run: async (input, ctx) => {
            ctx.progress({ step: 'package' });
            return ok({ artifact: `${input.name}.zip` });
          },
        },
        model,
      },
      { validate: 'full' }
    );
    const forwarded = createTestWire(contract, forwardController(contract, upstream.client), {
      validate: 'full',
    });

    try {
      const download = await forwarded.client.download({ id: 'known' });
      expect(download.success).toBe(true);
      if (!download.success) return;
      expect(download.data.meta).toMatchObject({ name: 'known.txt' });
      await expect(download.data.bytes()).resolves.toEqual(textEncoder.encode('hello world'));

      await expect(
        forwarded.client.upload(
          { id: 'upload' },
          {
            name: 'upload.txt',
            mimeType: 'text/plain',
            size: 7,
            source: chunks(textEncoder.encode('payload')),
          }
        )
      ).resolves.toEqual(ok({ id: 'upload', text: 'payload' }));

      await expect(forwarded.client.output.handle(key).snapshot()).resolves.toMatchObject({
        data: { text: 'forwarded log' },
      });
      const streamed: Array<{ message: string }> = [];
      const unsubscribe = await forwarded.client.events.subscribe(key, {
        onEvent: (event) => streamed.push(event),
      });
      await waitFor(() => events.resolve(key).subscriberCount === 1);
      events.emit(key, { message: 'forwarded event' });
      await waitFor(() => streamed.length === 1);
      unsubscribe();
      expect(streamed).toEqual([{ message: 'forwarded event' }]);

      await expect(forwarded.client.model.state(key, 'state').snapshot()).resolves.toMatchObject({
        data: { count: 1 },
      });
      await expect(
        forwarded.client.model.mutate('bump', { key, input: { amount: 2 } })
      ).resolves.toMatchObject({ success: true, data: { data: { count: 3 } } });
      await expect(forwarded.client.model.state(key, 'state').snapshot()).resolves.toMatchObject({
        data: { count: 3 },
      });

      const { jobId } = await forwarded.client.task.start({ name: 'demo' });
      const jobSnapshot = await forwarded.client.task.handle(jobId).snapshot();
      expect(['running', 'succeeded']).toContain(jobSnapshot.data.status);
    } finally {
      forwarded.dispose();
      upstream.dispose();
      events.dispose();
      await model.dispose();
    }
  });

  it('rebinds live endpoint definitions when mounting a client under a namespace', async () => {
    const key = { id: 'known' };
    const model = counterModelProvider({ count: 1 });
    const events = createEventStreamHost(contract.events);
    const upstream = createTestWire(contract, {
      download: ({ id }) =>
        ok({
          meta: { name: `${id}.txt`, mimeType: 'text/plain', size: 11 },
          source: chunks(textEncoder.encode('hello world')),
        }),
      upload: async ({ id }, file) => ok({ id, text: textDecoder.decode(await file.bytes()) }),
      output: () => createLogSource('forwarded log'),
      events,
      task: {
        run: async ({ name }) => ok({ artifact: `${name}.zip` }),
      },
      model,
    });
    const aggregateContract = defineContract({ nested: contract });
    const forwarded = createTestWire(aggregateContract, {
      nested: forwardContractImpl(aggregateContract.nested, upstream.client),
    });

    try {
      expect(aggregateContract.nested.model.id).toBe('nested.model');
      expect(upstream.client.model.def.id).toBe('model');
      await expect(
        forwarded.client.nested.model.state(key, 'state').snapshot()
      ).resolves.toMatchObject({ data: { count: 1 } });
      await expect(
        forwarded.client.nested.model.mutate('bump', { key, input: { amount: 2 } })
      ).resolves.toMatchObject({
        success: true,
        data: {
          data: { count: 3 },
          cursors: [expect.objectContaining({ model: 'nested.model.state' })],
        },
      });

      const download = await forwarded.client.nested.download({ id: 'known' });
      expect(download.success).toBe(true);
      if (!download.success) return;
      await expect(download.data.bytes()).resolves.toEqual(textEncoder.encode('hello world'));
    } finally {
      forwarded.dispose();
      upstream.dispose();
      events.dispose();
      await model.dispose();
    }
  });

  it('forwards upstream event-stream gap and terminal error lifecycle', async () => {
    const lifecycleContract = defineContract({
      events: eventStream({
        key: z.object({ id: z.string() }),
        event: z.object({ message: z.string() }),
      }),
    });
    const source = new LifecycleSource();
    const upstream = createTestWire(lifecycleContract, { events: () => source });
    const forwarded = createTestWire(
      lifecycleContract,
      forwardController(lifecycleContract, upstream.client)
    );
    const gaps: string[] = [];
    const errors: Array<{ code: string; retrying: boolean }> = [];
    const unsubscribe = await forwarded.client.events.subscribe(
      { id: 'known' },
      {
        onEvent: () => {},
        onGap: () => gaps.push('gap'),
        onError: (error, context) => errors.push({ code: error.code, retrying: context.retrying }),
      }
    );

    try {
      source.gap();
      await waitFor(() => gaps.length === 1);

      source.error(false);
      await waitFor(() => errors.length === 1);

      expect(gaps).toEqual(['gap']);
      expect(errors).toEqual([{ code: 'UNKNOWN_TOPIC', retrying: false }]);
    } finally {
      unsubscribe();
      forwarded.dispose();
      upstream.dispose();
    }
  });
});

function createLogSource(text: string): LiveSource {
  return {
    snapshot: () => ({
      generation: 1,
      sequence: 0,
      timestamp: 0,
      data: { baseOffset: 0, text, truncated: false },
    }),
    subscribe(): Unsubscribe {
      return () => {};
    },
  };
}

class LifecycleSource implements LiveSource {
  private options: LiveSubscribeOptions | undefined;

  snapshot() {
    return {
      generation: 1,
      sequence: 0,
      timestamp: 0,
      data: {},
    };
  }

  subscribe(_cb: (update: LiveUpdate) => void, options?: LiveSubscribeOptions): Unsubscribe {
    this.options = options;
    return () => {
      this.options = undefined;
    };
  }

  gap(): void {
    this.options?.onGap?.();
  }

  error(retrying: boolean): void {
    this.options?.onError?.(new WireError('UNKNOWN_TOPIC', 'upstream topic failed'), { retrying });
  }
}

async function* chunks(data: Uint8Array): AsyncIterable<Uint8Array> {
  yield data;
}
