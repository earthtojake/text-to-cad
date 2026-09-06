import { describe, expect, it } from 'vitest';
import { KeyedMutex } from './keyed-mutex';

describe('KeyedMutex', () => {
  it('serializes concurrent calls on the same key', async () => {
    const mutex = new KeyedMutex();
    const order: number[] = [];

    let resolveFirst!: () => void;
    const first = mutex.runExclusive('k', () => {
      return new Promise<void>((resolve) => {
        resolveFirst = resolve;
        order.push(1);
      });
    });

    const second = mutex.runExclusive('k', async () => {
      order.push(2);
    });

    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(order).toEqual([1]);

    resolveFirst();
    await first;
    await second;
    expect(order).toEqual([1, 2]);
  });

  it('runs calls on different keys in parallel', async () => {
    const mutex = new KeyedMutex();
    const running: string[] = [];

    let resolveA!: () => void;
    let resolveB!: () => void;

    const a = mutex.runExclusive('a', () => {
      return new Promise<void>((resolve) => {
        resolveA = resolve;
        running.push('a');
      });
    });

    const b = mutex.runExclusive('b', () => {
      return new Promise<void>((resolve) => {
        resolveB = resolve;
        running.push('b');
      });
    });

    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(running).toContain('a');
    expect(running).toContain('b');

    resolveA();
    resolveB();
    await Promise.all([a, b]);
  });

  it('does not block subsequent calls on the same key after a rejection', async () => {
    const mutex = new KeyedMutex();
    const results: string[] = [];

    await expect(mutex.runExclusive('k', () => Promise.reject(new Error('boom')))).rejects.toThrow(
      'boom'
    );

    await mutex.runExclusive('k', async () => {
      results.push('recovered');
    });

    expect(results).toEqual(['recovered']);
  });

  it('propagates return values', async () => {
    const mutex = new KeyedMutex();

    const result = await mutex.runExclusive('k', async () => 42);
    expect(result).toBe(42);
  });
});
