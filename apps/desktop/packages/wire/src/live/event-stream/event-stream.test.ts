import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { eventStream, resourcedStream } from '../../api';
import { eventFromUpdate } from './client';
import { createEventStreamHost, EventStreamSource } from './source';

describe('EventStreamSource', () => {
  it('emits envelope-correct event updates while attached', () => {
    const source = new EventStreamSource<{ message: string }>({ generation: 1000 });
    const updates: unknown[] = [];
    source.subscribe((update) => updates.push(update));

    source.emit({ message: 'hello' });

    expect(updates).toEqual([
      {
        generation: 1000,
        baseSequence: 0,
        sequence: 1,
        timestamp: expect.any(Number),
        delta: { event: { message: 'hello' } },
      },
    ]);
    expect(eventFromUpdate<{ message: string }>(updates[0] as never)).toEqual({ message: 'hello' });
  });

  it('drops events when there are no subscribers', () => {
    const source = new EventStreamSource<{ message: string }>({ generation: 1000 });
    const updates: unknown[] = [];

    source.emit({ message: 'early' });
    source.subscribe((update) => updates.push(update));
    source.emit({ message: 'late' });

    expect(updates).toHaveLength(1);
    expect(eventFromUpdate<{ message: string }>(updates[0] as never)).toEqual({ message: 'late' });
    expect(source.snapshot().sequence).toBe(1);
  });

  it('calls lifecycle hooks on first subscriber and last detach', () => {
    const onFirst = vi.fn();
    const onEmpty = vi.fn();
    const source = new EventStreamSource({ onFirst, onEmpty });
    const first = source.subscribe(() => {});
    const second = source.subscribe(() => {});

    expect(onFirst).toHaveBeenCalledOnce();

    first();
    expect(onEmpty).not.toHaveBeenCalled();

    second();
    second();

    expect(onEmpty).toHaveBeenCalledOnce();
  });

  it('keeps plain stream subscription synchronous', () => {
    const source = new EventStreamSource();

    const unsubscribe = source.subscribe(() => {});

    expect(unsubscribe).toBeTypeOf('function');
    unsubscribe();
  });
});

describe('createEventStreamHost', () => {
  const contract = eventStream({
    key: z.object({ id: z.string() }),
    event: z.object({ message: z.string() }),
  });

  it('isolates events by key', () => {
    const host = createEventStreamHost(contract);
    const first: unknown[] = [];
    const second: unknown[] = [];
    host.resolve({ id: 'first' }).subscribe((update) => first.push(eventFromUpdate(update)));
    host.resolve({ id: 'second' }).subscribe((update) => second.push(eventFromUpdate(update)));

    host.emit({ id: 'first' }, { message: 'one' });
    host.emit({ id: 'second' }, { message: 'two' });

    expect(first).toEqual([{ message: 'one' }]);
    expect(second).toEqual([{ message: 'two' }]);
  });

  it('drops idle sources after the last subscriber detaches', () => {
    const host = createEventStreamHost(contract);
    const source = host.resolve({ id: 'known' });
    const unsubscribe = source.subscribe(() => {});

    unsubscribe();

    expect(host.resolve({ id: 'known' })).not.toBe(source);
  });

  it('calls onEmpty when the last source subscriber detaches', () => {
    const onEmpty = vi.fn();
    const source = new EventStreamSource({ onEmpty });
    const unsubscribe = source.subscribe(() => {});

    unsubscribe();

    expect(onEmpty).toHaveBeenCalledOnce();
  });

  it('calls host lifecycle hooks for first attach and last detach per key', () => {
    const activeKeys: Array<{ id: string }> = [];
    const idleKeys: Array<{ id: string }> = [];
    const host = createEventStreamHost(contract, {
      onActive: (key) => activeKeys.push(key),
      onIdle: (key) => idleKeys.push(key),
    });
    const source = host.resolve({ id: 'known' });
    const first = source.subscribe(() => {});
    const second = source.subscribe(() => {});

    expect(activeKeys).toEqual([{ id: 'known' }]);
    expect(idleKeys).toEqual([]);

    first();
    expect(idleKeys).toEqual([]);

    second();
    expect(idleKeys).toEqual([{ id: 'known' }]);

    host.resolve({ id: 'known' }).subscribe(() => {})();

    expect(activeKeys).toEqual([{ id: 'known' }, { id: 'known' }]);
    expect(idleKeys).toEqual([{ id: 'known' }, { id: 'known' }]);
  });
});

describe('resourced event streams', () => {
  const contract = resourcedStream({
    key: z.object({ id: z.string() }),
    event: z.object({ message: z.string() }),
  });

  it('shares the resolved activation barrier with late subscribers', async () => {
    const dispose = vi.fn();
    const activate = vi.fn(async () => dispose);
    const host = createEventStreamHost(contract, { activate });
    const source = host.resolve({ id: 'known' });

    const first = await source.subscribe(() => {});
    const second = await source.subscribe(() => {});

    expect(activate).toHaveBeenCalledOnce();
    first();
    expect(dispose).not.toHaveBeenCalled();
    second();
    expect(dispose).toHaveBeenCalledOnce();
  });

  it('registers subscribers before activation can emit', async () => {
    const updates: unknown[] = [];
    const host = createEventStreamHost(contract, {
      activate: async (key) => {
        host.emit(key, { message: 'during activation' });
        return () => {};
      },
    });

    const unsubscribe = await host
      .resolve({ id: 'known' })
      .subscribe((update) => updates.push(eventFromUpdate(update)));

    expect(updates).toEqual([{ message: 'during activation' }]);
    unsubscribe();
  });

  it('rejects every activation waiter and retries with a fresh activation', async () => {
    const failure = new Error('startup failed');
    const activate = vi
      .fn<() => Promise<() => void>>()
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce(() => {});
    const host = createEventStreamHost(contract, { activate });
    const source = host.resolve({ id: 'known' });

    const first = source.subscribe(() => {});
    const second = source.subscribe(() => {});
    await expect(first).rejects.toBe(failure);
    await expect(second).rejects.toBe(failure);
    expect(source.subscriberCount).toBe(0);

    const unsubscribe = await host.resolve({ id: 'known' }).subscribe(() => {});
    expect(activate).toHaveBeenCalledTimes(2);
    unsubscribe();
  });

  it('disposes an activation that settles after the host is disposed', async () => {
    const activation = deferred<() => void>();
    const dispose = vi.fn();
    const host = createEventStreamHost(contract, { activate: () => activation.promise });
    const subscription = host.resolve({ id: 'known' }).subscribe(() => {});

    host.dispose();
    activation.resolve(dispose);
    const unsubscribe = await subscription;

    expect(dispose).toHaveBeenCalledOnce();
    unsubscribe();
    expect(dispose).toHaveBeenCalledOnce();
  });
});

function deferred<T>(): {
  promise: Promise<T>;
  resolve(value: T): void;
} {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
