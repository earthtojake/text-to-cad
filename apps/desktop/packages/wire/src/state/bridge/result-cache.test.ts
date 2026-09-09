import { ok } from '@emdash/shared';
import { deferred } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import { MutationResultCache } from './result-cache';

describe('MutationResultCache', () => {
  it('returns settled results for duplicate mutation IDs', async () => {
    const handler = vi.fn(async () => ok({ data: 'done', cursors: [] }));
    const cache = new MutationResultCache();

    const first = await cache.run('m1', handler);
    const second = await cache.run('m1', handler);

    expect(first).toEqual(second);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('shares in-flight executions for concurrent duplicate mutation IDs', async () => {
    const gate = deferred<ReturnType<typeof ok<{ data: string; cursors: [] }>>>();
    const handler = vi.fn(async () => gate.promise);
    const cache = new MutationResultCache();

    const first = cache.run('m1', handler);
    const second = cache.run('m1', handler);
    gate.resolve(ok({ data: 'done', cursors: [] }));

    await expect(Promise.all([first, second])).resolves.toEqual([
      ok({ data: 'done', cursors: [] }),
      ok({ data: 'done', cursors: [] }),
    ]);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('does not cache thrown errors', async () => {
    const handler = vi
      .fn<() => Promise<ReturnType<typeof ok<{ data: string; cursors: [] }>>>>()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(ok({ data: 'done', cursors: [] }));
    const cache = new MutationResultCache();

    await expect(cache.run('m1', handler)).rejects.toThrow('boom');
    await expect(cache.run('m1', handler)).resolves.toEqual(ok({ data: 'done', cursors: [] }));
    expect(handler).toHaveBeenCalledTimes(2);
  });

  it('evicts entries after ttl', async () => {
    let now = 0;
    const handler = vi.fn(async () => ok({ data: 'done', cursors: [] }));
    const cache = new MutationResultCache({ ttlMs: 10, now: () => now });

    await cache.run('m1', handler);
    now = 11;
    await cache.run('m1', handler);

    expect(handler).toHaveBeenCalledTimes(2);
  });
});
