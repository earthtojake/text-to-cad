import { describe, expect, it, vi } from 'vitest';
import { createEmitter } from './emitter';

describe('Emitter', () => {
  it('delivers values to all subscribers and supports unsubscribe', () => {
    const emitter = createEmitter<number>();
    const first: number[] = [];
    const second: number[] = [];

    const unsubFirst = emitter.subscribe((value) => first.push(value));
    emitter.subscribe((value) => second.push(value));
    expect(emitter.size).toBe(2);

    emitter.emit(1);
    unsubFirst();
    emitter.emit(2);

    expect(first).toEqual([1]);
    expect(second).toEqual([1, 2]);
    expect(emitter.size).toBe(1);
  });

  it('tolerates unsubscribe during emit', () => {
    const emitter = createEmitter<string>();
    const seen: string[] = [];
    const unsubscribe = emitter.subscribe(() => {
      unsubscribe();
    });
    emitter.subscribe((value) => seen.push(value));

    emitter.emit('a');
    emitter.emit('b');

    expect(seen).toEqual(['a', 'b']);
    expect(emitter.size).toBe(1);
  });

  it('clears all subscribers', () => {
    const emitter = createEmitter<number>();
    const seen: number[] = [];
    emitter.subscribe((value) => seen.push(value));

    emitter.clear();
    emitter.emit(1);

    expect(seen).toEqual([]);
    expect(emitter.size).toBe(0);
  });

  it('isolates subscriber failures and continues delivery', () => {
    const error = new Error('boom');
    const onSubscriberError = vi.fn();
    const emitter = createEmitter<number>({ onSubscriberError });
    const seen: number[] = [];
    emitter.subscribe(() => {
      throw error;
    });
    emitter.subscribe((value) => seen.push(value));

    expect(() => emitter.emit(1)).not.toThrow();

    expect(seen).toEqual([1]);
    expect(onSubscriberError).toHaveBeenCalledWith({ error });
  });

  it('does not expose emitted values to the subscriber error reporter', () => {
    const onSubscriberError = vi.fn();
    const emitter = createEmitter<{ secret: string }>({ onSubscriberError });
    emitter.subscribe(() => {
      throw new Error('boom');
    });

    emitter.emit({ secret: 'do-not-report' });

    expect(onSubscriberError).toHaveBeenCalledTimes(1);
    expect(onSubscriberError.mock.calls[0]?.[0]).not.toHaveProperty('value');
  });

  it('isolates subscriber error reporter failures', () => {
    const emitter = createEmitter<number>({
      onSubscriberError() {
        throw new Error('report failed');
      },
    });
    const seen: number[] = [];
    emitter.subscribe(() => {
      throw new Error('boom');
    });
    emitter.subscribe((value) => seen.push(value));

    expect(() => emitter.emit(1)).not.toThrow();

    expect(seen).toEqual([1]);
  });
});
