import { describe, expect, it, vi } from 'vitest';
import { deferred } from '../testing';
import { compose } from './compose';
import { deduplicate } from './deduplicate';

describe('deduplicate', () => {
  it('shares one in-flight execution for identical inputs', async () => {
    const gate = deferred<number>();
    const spy = vi.fn();
    const handler = async (_input: { id: string }, _meta: { signal?: AbortSignal }) => {
      spy();
      return await gate.promise;
    };
    const deduped = compose(handler, [deduplicate()]);

    const first = deduped({ id: 'same' }, {});
    const second = deduped({ id: 'same' }, {});

    expect(spy).toHaveBeenCalledTimes(1);
    gate.resolve(42);
    await expect(Promise.all([first, second])).resolves.toEqual([42, 42]);
  });

  it('uses stable JSON identity and supports custom keys', async () => {
    const spy = vi.fn();
    const handler = async (
      input: { id?: string; a?: number; b?: number },
      _meta: { signal?: AbortSignal }
    ) => {
      spy();
      return input.id ?? 'ok';
    };
    const stable = compose(handler, [deduplicate()]);
    const custom = compose(handler, [deduplicate({ key: (input) => input.id ?? '' })]);

    await expect(
      Promise.all([stable({ a: 1, b: 2 }, {}), stable({ b: 2, a: 1 }, {})])
    ).resolves.toEqual(['ok', 'ok']);
    await expect(
      Promise.all([custom({ id: 'same', a: 1 }, {}), custom({ id: 'same', a: 2 }, {})])
    ).resolves.toEqual(['same', 'same']);
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('does not cache completions or rejections', async () => {
    const spy = vi.fn();
    const handler = async (_input: { id: string }, _meta: { signal?: AbortSignal }) => {
      spy();
      if (spy.mock.calls.length === 1) throw new Error('boom');
      return 'ok';
    };
    const deduped = compose(handler, [deduplicate()]);

    await expect(deduped({ id: 'same' }, {})).rejects.toThrow('boom');
    await expect(deduped({ id: 'same' }, {})).resolves.toBe('ok');
    await expect(deduped({ id: 'same' }, {})).resolves.toBe('ok');
    expect(spy).toHaveBeenCalledTimes(3);
  });

  it('lets one caller cancel without aborting shared work', async () => {
    const gate = deferred<string>();
    let sharedSignalAborted = false;
    const handler = async (_input: { id: string }, context: { signal?: AbortSignal }) => {
      context.signal?.addEventListener('abort', () => {
        sharedSignalAborted = true;
      });
      return await gate.promise;
    };
    const deduped = compose(handler, [deduplicate()]);
    const abort = new AbortController();

    const first = deduped({ id: 'same' }, { signal: abort.signal });
    const second = deduped({ id: 'same' }, {});
    abort.abort(new Error('caller cancelled'));

    await expect(first).rejects.toThrow('caller cancelled');
    expect(sharedSignalAborted).toBe(false);
    gate.resolve('ok');
    await expect(second).resolves.toBe('ok');
  });

  it('aborts shared work when the final waiter leaves if configured', async () => {
    let resolveAborted!: () => void;
    const aborted = new Promise<void>((resolve) => {
      resolveAborted = resolve;
    });
    const handler = async (_input: { id: string }, context: { signal?: AbortSignal }) => {
      context.signal?.addEventListener('abort', () => resolveAborted(), { once: true });
      await new Promise<never>(() => {});
    };
    const deduped = compose(handler, [deduplicate({ cancelWhenUnused: true })]);
    const abort = new AbortController();

    const pending = deduped({ id: 'same' }, { signal: abort.signal });
    abort.abort(new Error('gone'));

    await expect(pending).rejects.toThrow('gone');
    await expect(aborted).resolves.toBeUndefined();
  });

  it('starts fresh work after canceling an unused keyed request', async () => {
    const firstStarted = deferred<void>();
    const finishFirst = deferred<void>();
    let calls = 0;
    const handler = async (_input: { id: string }, context: { signal?: AbortSignal }) => {
      calls += 1;
      if (calls > 1) return 'fresh';
      firstStarted.resolve();
      await new Promise<void>((resolve) => {
        context.signal?.addEventListener('abort', () => resolve(), { once: true });
      });
      await finishFirst.promise;
      throw context.signal?.reason;
    };
    const deduped = compose(handler, [deduplicate({ cancelWhenUnused: true })]);
    const abort = new AbortController();
    const first = deduped({ id: 'same' }, { signal: abort.signal });
    await firstStarted.promise;

    abort.abort(new Error('gone'));
    await expect(first).rejects.toThrow('gone');
    await expect(deduped({ id: 'same' }, {})).resolves.toBe('fresh');
    expect(calls).toBe(2);
    finishFirst.resolve();
  });
});
