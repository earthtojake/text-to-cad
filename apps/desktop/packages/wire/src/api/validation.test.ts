import { err, ok } from '@emdash/shared';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { createController } from '../rpc/controller';
import { expose } from '../state/bridge/expose';
import { cell, snapshot } from '../state/core';
import { createTestWire } from '../testing';
import { type LiveSource } from './channel';
import {
  defineContract,
  downloadFile,
  liveLog,
  liveModel,
  liveState,
  mutation,
  procedure,
} from './define';
import { WireError } from './protocol';
import { encodeTopic } from './topics';
import { applyValidation, defaultValidatePolicy } from './validation';

const source: LiveSource = {
  snapshot: () => ({ generation: 1, sequence: 0, timestamp: 0, data: undefined }),
  subscribe: () => () => {},
};

describe('defaultValidatePolicy', () => {
  it('is full outside production and inputs-only in production', () => {
    expect(defaultValidatePolicy({ NODE_ENV: 'production' })).toBe('inputs');
    expect(defaultValidatePolicy({ NODE_ENV: 'development' })).toBe('full');
    expect(defaultValidatePolicy({ NODE_ENV: 'test' })).toBe('full');
    expect(defaultValidatePolicy({})).toBe('full');
  });
});

describe('controller validation', () => {
  it('applies full validation by default in tests, same as dev', async () => {
    const contract = defineContract({
      invalid: procedure({ input: z.void().optional(), output: z.object({ value: z.string() }) }),
    });
    const controller = createController(contract, {
      invalid: () => ({ value: 1 }) as never,
    });

    await expect(controller.call('invalid', undefined)).rejects.toThrow();
  });

  it('validates procedure inputs and full-mode outputs', async () => {
    const contract = defineContract({
      echo: procedure({
        input: z.object({ value: z.string() }),
        output: z.object({ value: z.string() }),
      }),
    });
    const controller = createController(
      contract,
      {
        echo: (input) => ({ value: input.value.toUpperCase() }),
      },
      { validate: 'full' }
    );

    await expect(controller.call('echo', { value: 'ok' })).resolves.toEqual({ value: 'OK' });
    await expect(controller.call('echo', { value: 1 })).rejects.toThrow();
  });

  it('rejects invalid outputs only in full mode', async () => {
    const contract = defineContract({
      invalid: procedure({ input: z.void().optional(), output: z.object({ value: z.string() }) }),
    });
    const impl = {
      invalid: () => ({ value: 1 }) as never,
    };

    await expect(
      createController(contract, impl, { validate: 'inputs' }).call('invalid', undefined)
    ).resolves.toEqual({ value: 1 });
    await expect(
      createController(contract, impl, { validate: 'full' }).call('invalid', undefined)
    ).rejects.toThrow();
  });

  it('validates live keys and re-encodes parsed values before resolving topics', () => {
    const contract = defineContract({
      output: liveLog({ key: z.object({ id: z.string().trim() }) }),
    });
    const seen: unknown[] = [];
    const controller = createController(
      contract,
      {
        output: (key) => {
          seen.push(key);
          return source;
        },
      },
      { validate: 'inputs' }
    );

    expect(controller.resolveLive(encodeTopic(contract.output.id, { id: ' known ' }))).toBe(source);
    expect(seen).toEqual([{ id: 'known' }]);
    expect(() => controller.resolveLive(encodeTopic(contract.output.id, { id: 1 }))).toThrow();
  });

  it('validates live model mutation envelopes and outputs', async () => {
    const contract = defineContract({
      group: liveModel({
        key: z.object({ id: z.string().trim() }),
        states: { item: liveState({ data: z.object({ value: z.string() }) }) },
        mutations: {
          set: mutation({
            input: z.object({ value: z.string().trim() }),
            data: z.object({ value: z.string() }),
            error: z.object({ type: z.string() }),
          }),
        },
      }),
    });
    const item = cell({ value: 'old' });
    const provider = expose(
      contract.group,
      { item: () => item },
      {
        mutations: {
          async set(context) {
            const revision = item.update(() => ({ value: context.input.value }), {
              mutationIds: [context.mutationId],
            });
            await context.observed('item', revision);
            return ok({ value: context.input.value });
          },
        },
      }
    );
    const controller = createController(contract, { group: provider }, { validate: 'full' });

    await expect(
      controller.call('group.set', { key: { id: ' known ' }, input: { value: ' next ' } })
    ).resolves.toMatchObject({ success: true, data: { data: { value: 'next' } } });
    expect(snapshot(item).value).toEqual({ value: 'next' });
    await expect(
      controller.call('group.set', { key: { id: 'known' }, input: { value: 1 } })
    ).rejects.toThrow();
  });

  it('round-trips void live model inputs through nested validation layers', async () => {
    const contract = defineContract({
      group: liveModel({
        key: z.object({ id: z.string() }),
        states: { item: liveState({ data: z.object({ touched: z.boolean() }) }) },
        mutations: {
          touch: mutation({
            input: z.void().optional(),
            data: z.void(),
            error: z.object({ type: z.string() }),
          }),
        },
      }),
    });
    const item = cell({ touched: false });
    const provider = expose(
      contract.group,
      { item: () => item },
      {
        mutations: {
          async touch(context) {
            const revision = item.update(() => ({ touched: true }), {
              mutationIds: [context.mutationId],
            });
            await context.observed('item', revision);
            return ok<void>();
          },
        },
      }
    );
    const controller = applyValidation(
      contract,
      createController(contract, { group: provider }, { validate: 'full' }),
      'inputs'
    );

    await expect(
      controller.call('group.touch', { key: { id: 'known' }, input: undefined })
    ).resolves.toMatchObject({ success: true });
    expect(snapshot(item).value).toEqual({ touched: true });
  });

  it('accepts void mutation results whose data key was dropped by JSON transports', async () => {
    const contract = defineContract({
      group: liveModel({
        key: z.object({ id: z.string() }),
        states: { item: liveState({ data: z.object({ value: z.string() }) }) },
        mutations: {
          touch: mutation({
            input: z.object({}),
            data: z.void(),
            error: z.object({ type: z.string() }),
          }),
          set: mutation({
            input: z.object({}),
            data: z.object({ value: z.string() }),
            error: z.object({ type: z.string() }),
          }),
        },
      }),
    });
    const jsonRoundTrippedVoidResult = JSON.parse(
      JSON.stringify(ok({ data: undefined, cursors: [] }))
    ) as unknown;
    const controller = applyValidation(
      contract,
      {
        call: async () => jsonRoundTrippedVoidResult,
        resolveLive: () => null,
        acquireLive: () => null,
      },
      'full'
    );

    await expect(
      controller.call('group.touch', { key: { id: 'known' }, input: {} })
    ).resolves.toEqual({ success: true, data: { cursors: [] } });
    await expect(
      controller.call('group.set', { key: { id: 'known' }, input: {} })
    ).rejects.toThrow();
  });

  it('validates download file metadata while preserving blob transfer handles', async () => {
    const contract = defineContract({
      download: downloadFile({
        input: z.object({ id: z.string() }),
        meta: z.object({
          name: z.string(),
          mimeType: z.literal('text/plain'),
          size: z.number(),
        }),
        error: z.object({ type: z.string() }),
      }),
    });

    const wire = createTestWire(
      contract,
      {
        download: ({ id }) =>
          id === 'missing'
            ? err({ type: 'missing' })
            : ok({
                meta: { name: `${id}.txt`, mimeType: 'text/plain', size: 2 },
                source: chunks(new TextEncoder().encode('ok')),
              }),
      },
      { validate: 'full' }
    );

    try {
      const result = await wire.client.download({ id: 'known' });

      expect(result.success).toBe(true);
      if (!result.success) return;
      expect(result.data.meta).toEqual({ name: 'known.txt', mimeType: 'text/plain', size: 2 });
      await expect(result.data.bytes()).resolves.toEqual(new TextEncoder().encode('ok'));
      await expect(wire.client.download({ id: 'missing' })).resolves.toEqual(
        err({ type: 'missing' })
      );
    } finally {
      wire.dispose();
    }
  });

  it('passes unknown paths and topics through to the inner controller', async () => {
    const contract = defineContract({
      known: procedure({ input: z.void().optional(), output: z.void() }),
    });
    const controller = applyValidation(
      contract,
      {
        call(path) {
          throw new WireError('UNKNOWN_PROCEDURE', path);
        },
        resolveLive(topic) {
          return topic === 'dynamic.topic' ? source : null;
        },
        acquireLive() {
          return null;
        },
      },
      'full'
    );

    await expect(controller.call('unknown', undefined)).rejects.toMatchObject({
      code: 'UNKNOWN_PROCEDURE',
      message: 'unknown',
    });
    expect(controller.resolveLive('dynamic.topic')).toBe(source);
  });
});

async function* chunks(data: Uint8Array): AsyncIterable<Uint8Array> {
  yield data;
}
