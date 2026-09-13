import { ok } from '@emdash/shared';
import { createScope } from '@emdash/shared/concurrency';
import { createManualClock } from '@emdash/shared/testing';
import { describe, expect, expectTypeOf, it } from 'vitest';
import { z } from 'zod';
import { liveModel, liveState, mutation, type LiveModelDef } from '../../api';
import { cell, derived, family, flushStateTurn, snapshot } from '../core';
import { query } from '../query';
import { settleAsync } from '../testing';
import { expose } from './expose';

const contract = liveModel({
  key: z.object({ id: z.string() }),
  states: {
    value: liveState({ data: z.object({ count: z.number() }) }),
  },
  mutations: {
    increment: mutation({
      input: z.object({ by: z.number() }),
      data: z.void(),
      error: z.never(),
    }),
  },
});

const transcriptContract = liveModel({
  key: z.void(),
  states: {
    transcript: liveState({
      data: z.object({
        turn: z.object({
          messages: z.array(z.object({ text: z.string() })),
        }),
      }),
    }),
  },
  mutations: {},
});

describe('state expose bridge', () => {
  it('accepts typed live models with mutations without casts', () => {
    expectTypeOf(contract).toMatchTypeOf<LiveModelDef>();
  });

  it('waits for a cold query before resolving an acquired live source', async () => {
    const clock = createManualClock();
    const scope = createScope();
    const model = query({
      fetch: async () => ({ count: 1 }),
      debounceMs: 0,
      clock,
      scope,
    });
    const provider = expose(contract, { value: model });
    const lease = provider.acquireState({ id: 'one' }, 'value');
    let ready = false;
    const readySource = lease.ready().then((source) => {
      ready = true;
      return source;
    });

    await settleAsync();
    expect(ready).toBe(false);

    await clock.advanceBy(0);
    const source = await readySource;
    expect((await source.snapshot()).data).toEqual({ count: 1 });

    await lease.release();
    await provider.dispose();
    await scope.dispose();
  });

  it('waits for an async state resolver before resolving an acquired live source', async () => {
    const resolved = deferred<ReturnType<typeof cell<{ count: number }>>>();
    const provider = expose(contract, {
      value: () => resolved.promise,
    });
    const lease = provider.acquireState({ id: 'one' }, 'value');
    let ready = false;
    const readySource = lease.ready().then((source) => {
      ready = true;
      return source;
    });

    await settleAsync();
    expect(ready).toBe(false);

    const state = cell({ count: 4 });
    resolved.resolve(state);
    const source = await readySource;

    expect((await source.snapshot()).data).toEqual({ count: 4 });

    await lease.release();
    await provider.dispose();
  });

  it('releases upstream query demand after the last lease lingers out', async () => {
    const clock = createManualClock();
    let count = 0;
    const provider = expose(
      contract,
      {
        value: (_key, scope) =>
          query({
            fetch: async () => {
              count += 1;
              return { count };
            },
            debounceMs: 0,
            revalidateEveryMs: 10,
            clock,
            scope,
          }),
      },
      { clock, lingerMs: 5 }
    );

    const lease = provider.acquireState({ id: 'one' }, 'value');
    await clock.advanceBy(0);
    await lease.ready();
    await lease.release();
    await clock.advanceBy(5);
    await clock.advanceBy(20);

    expect(count).toBe(1);
    await provider.dispose();
  });

  it('observes mutation revisions through a derived exposed state', async () => {
    const base = cell({ count: 0 });
    const value = derived(() => ({ count: snapshot(base).value.count }));
    const provider = expose(
      contract,
      { value },
      {
        mutations: {
          async increment(context) {
            const revision = base.update(
              (previous) => ({ count: previous.count + context.input.by }),
              { mutationIds: [context.mutationId] }
            );
            await context.observed('value', revision);
            return ok<void>();
          },
        },
      }
    );
    const lease = provider.acquireState({ id: 'one' }, 'value');
    await lease.ready();

    const resultPromise = provider.runMutation('increment', {
      key: { id: 'one' },
      input: { by: 2 },
      mutationId: 'm1',
    });
    await settleAsync();
    flushStateTurn();
    const result = await resultPromise;

    expect(result.success).toBe(true);
    if (!result.success) throw new Error('Expected mutation success');
    expect(result.data.cursors).toHaveLength(1);
    expect((await (await lease.ready()).snapshot()).data).toEqual({ count: 2 });

    await lease.release();
    await provider.dispose();
  });

  it('dedupes duplicate mutation ids while the handler is in flight', async () => {
    const base = cell({ count: 0 });
    const release = deferred<void>();
    let handlerCalls = 0;
    const deduped: string[] = [];
    const provider = expose(
      contract,
      { value: base },
      {
        mutations: {
          async increment(context) {
            handlerCalls += 1;
            await release.promise;
            const revision = base.update(
              (previous) => ({ count: previous.count + context.input.by }),
              { mutationIds: [context.mutationId] }
            );
            await context.observed('value', revision);
            return ok<void>();
          },
        },
        instrumentation: {
          mutationDeduped(event) {
            deduped.push(event.mutationId);
          },
        },
      }
    );

    const first = provider.runMutation('increment', {
      key: { id: 'one' },
      input: { by: 2 },
      mutationId: 'm1',
    });
    const second = provider.runMutation('increment', {
      key: { id: 'one' },
      input: { by: 2 },
      mutationId: 'm1',
    });
    await settleAsync();
    expect(handlerCalls).toBe(1);
    expect(deduped).toEqual(['m1']);

    release.resolve(undefined);
    const [firstResult, secondResult] = await Promise.all([first, second]);

    expect(firstResult).toEqual(secondResult);
    expect(handlerCalls).toBe(1);
    expect(snapshot(base).value).toEqual({ count: 2 });
    await provider.dispose();
  });

  it('keeps a family member retained while an exposed record is leased past linger', async () => {
    const clock = createManualClock();
    const key = { id: 'one' };
    let source = 1;
    let instances = 0;
    const models = family(
      (_key: typeof key, scope) => {
        instances += 1;
        return query({
          fetch: async () => ({ count: source }),
          debounceMs: 0,
          clock,
          scope,
        });
      },
      { clock, lingerMs: 5, name: 'expose-family-retention-test' }
    );
    const provider = expose(
      contract,
      {
        value: (memberKey, scope) => {
          scope.add(models.retain(memberKey));
          return models(memberKey);
        },
      },
      {
        clock,
        lingerMs: 5,
        mutations: {
          async increment(context) {
            source += context.input.by;
            await context.observed(
              'value',
              models(context.key).refresh({ mutationIds: [context.mutationId] })
            );
            return ok<void>();
          },
        },
      }
    );
    const lease = provider.acquireState(key, 'value');
    await clock.advanceBy(0);
    await lease.ready();

    await clock.advanceBy(20);
    const result = await provider.runMutation('increment', {
      key,
      input: { by: 2 },
      mutationId: 'm1',
    });

    expect(result.success).toBe(true);
    expect(instances).toBe(1);
    expect((await (await lease.ready()).snapshot()).data).toEqual({ count: 3 });

    await lease.release();
    await provider.dispose();
    await models.dispose();
  });

  it('disposes records created only by mutation observation after linger', async () => {
    const clock = createManualClock();
    const base = cell({ count: 0 });
    let disposed = 0;
    const provider = expose(
      contract,
      {
        value: (_key, scope) => {
          scope.add(() => {
            disposed += 1;
          });
          return base;
        },
      },
      {
        clock,
        lingerMs: 5,
        mutations: {
          async increment(context) {
            const revision = base.update(
              (previous) => ({ count: previous.count + context.input.by }),
              { mutationIds: [context.mutationId] }
            );
            await context.observed('value', revision);
            return ok<void>();
          },
        },
      }
    );

    const result = await provider.runMutation('increment', {
      key: { id: 'one' },
      input: { by: 2 },
      mutationId: 'm1',
    });
    expect(result.success).toBe(true);
    expect(disposed).toBe(0);

    await clock.advanceBy(5);
    expect(disposed).toBe(1);

    await provider.dispose();
  });

  it('can publish structural diffs instead of whole-value replacements', async () => {
    const state = cell({
      turn: {
        messages: [{ text: 'hello' }],
      },
    });
    const provider = expose(
      transcriptContract,
      { transcript: state },
      { publish: { transcript: 'diff' } }
    );
    const lease = provider.acquireState(undefined, 'transcript');
    const source = await lease.ready();
    const updates: unknown[] = [];
    const unsubscribe = await source.subscribe((update) => updates.push(update));

    state.set({
      turn: {
        messages: [{ text: 'hello world' }],
      },
    });
    flushStateTurn();

    expect(updates).toHaveLength(1);
    expect(updates[0]).toMatchObject({
      delta: [{ op: 'replace', path: ['turn', 'messages', 0, 'text'], value: 'hello world' }],
    });

    unsubscribe();
    await lease.release();
    await provider.dispose();
  });
});

function deferred<T>(): {
  promise: Promise<T>;
  resolve(value: T): void;
} {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}
