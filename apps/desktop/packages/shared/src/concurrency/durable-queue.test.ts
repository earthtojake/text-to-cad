import { deferred } from '@emdash/shared/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createDurableQueue } from './durable-queue';
import { createScope } from './scope';

type TestRow = {
  id: string;
  lane: string;
  ready?: boolean;
};

describe('createDurableQueue', () => {
  let scope: ReturnType<typeof createScope> | undefined;

  afterEach(async () => {
    await scope?.dispose();
  });

  it('runs lanes in parallel while preserving serial work within each lane', async () => {
    scope = createScope({ label: 'durable-queue-test' });
    const releaseA = deferred<void>();
    const calls: string[] = [];
    let rows: TestRow[] = [
      { id: 'a:1', lane: 'a' },
      { id: 'b:1', lane: 'b' },
      { id: 'b:2', lane: 'b' },
    ];
    const queue = createDurableQueue({
      scope,
      list: async () => rows,
      laneOf: (row) => row.lane,
      isRunnable: async () => true,
      run: async (row) => {
        calls.push(row.id);
        if (row.id === 'a:1') await releaseA.promise;
        rows = rows.filter((candidate) => candidate.id !== row.id);
      },
      onError: (error) => {
        throw error;
      },
    });

    queue.poke();
    await vi.waitFor(() => expect(calls).toEqual(['a:1', 'b:1', 'b:2']));
    expect(rows.map((row) => row.id)).toEqual(['a:1']);

    releaseA.resolve();
    await queue.waitForIdle();
    expect(rows).toEqual([]);
  });

  it('runs ready rows in created order within a lane', async () => {
    scope = createScope({ label: 'durable-queue-test' });
    const calls: string[] = [];
    let rows: TestRow[] = [
      { id: 'a:1', lane: 'a' },
      { id: 'a:2', lane: 'a' },
      { id: 'a:3', lane: 'a' },
    ];
    const queue = createDurableQueue({
      scope,
      list: async () => rows,
      laneOf: (row) => row.lane,
      isRunnable: async () => true,
      run: async (row) => {
        calls.push(row.id);
        rows = rows.filter((candidate) => candidate.id !== row.id);
      },
      onError: (error) => {
        throw error;
      },
    });

    queue.poke();
    await queue.waitForIdle();

    expect(calls).toEqual(['a:1', 'a:2', 'a:3']);
  });

  it('does not busy-loop skipped rows and revisits them on the next poke', async () => {
    scope = createScope({ label: 'durable-queue-test' });
    const calls: string[] = [];
    let ready = false;
    let rows: TestRow[] = [{ id: 'a:1', lane: 'a' }];
    const queue = createDurableQueue({
      scope,
      list: async () => rows,
      laneOf: (row) => row.lane,
      isRunnable: async () => ready,
      run: async (row) => {
        calls.push(row.id);
        rows = [];
      },
      onError: (error) => {
        throw error;
      },
    });

    queue.poke();
    await queue.waitForIdle();
    expect(calls).toEqual([]);

    ready = true;
    queue.poke();
    await queue.waitForIdle();
    expect(calls).toEqual(['a:1']);
  });
});
