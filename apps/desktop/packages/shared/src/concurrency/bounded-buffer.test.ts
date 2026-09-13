import { noopLogger, setRootLogger } from '@emdash/shared/logger';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createStubLogger } from '../testing';
import { createBoundedBuffer } from './bounded-buffer';

describe('createBoundedBuffer', () => {
  describe('ownership loss contract', () => {
    it('fires onDrop exactly once for the value evicted by drop-oldest overflow', () => {
      const onDrop = vi.fn();
      const buffer = createBoundedBuffer<string>({ capacity: 2, overflow: 'drop-oldest', onDrop });

      buffer.offer('a');
      buffer.offer('b');
      const result = buffer.offer('c');

      expect(result).toEqual({ kind: 'accepted', dropped: 'a' });
      expect(onDrop).toHaveBeenCalledTimes(1);
      expect(onDrop).toHaveBeenCalledWith('a');
      expect(buffer.toArray()).toEqual(['b', 'c']);
    });

    it('fires onDrop exactly once for the value discarded by drop-newest overflow', () => {
      const onDrop = vi.fn();
      const buffer = createBoundedBuffer<string>({ capacity: 1, overflow: 'drop-newest', onDrop });

      buffer.offer('a');
      const result = buffer.offer('b');

      expect(result).toEqual({ kind: 'dropped', value: 'b' });
      expect(onDrop).toHaveBeenCalledTimes(1);
      expect(onDrop).toHaveBeenCalledWith('b');
    });

    it('never fires onDrop on reject at capacity > 0 — the caller keeps the value', () => {
      const onDrop = vi.fn();
      const buffer = createBoundedBuffer<string>({ capacity: 1, overflow: 'reject', onDrop });

      buffer.offer('a');
      const result = buffer.offer('b');

      expect(result).toEqual({ kind: 'full' });
      expect(onDrop).not.toHaveBeenCalled();
    });

    it('never fires onDrop on reject at capacity 0 — the caller keeps the value', () => {
      const onDrop = vi.fn();
      const buffer = createBoundedBuffer<string>({ capacity: 0, overflow: 'reject', onDrop });

      const result = buffer.offer('a');

      expect(result).toEqual({ kind: 'full' });
      expect(onDrop).not.toHaveBeenCalled();
    });

    it('fires onDrop on drop-newest at capacity 0 — the buffer took responsibility and dropped', () => {
      const onDrop = vi.fn();
      const buffer = createBoundedBuffer<string>({ capacity: 0, overflow: 'drop-newest', onDrop });

      const result = buffer.offer('a');

      expect(result).toEqual({ kind: 'dropped', value: 'a' });
      expect(onDrop).toHaveBeenCalledTimes(1);
      expect(onDrop).toHaveBeenCalledWith('a');
    });

    it('drains every buffered value through onDrop exactly once on clear()', () => {
      const onDrop = vi.fn();
      const buffer = createBoundedBuffer<string>({ capacity: 3, overflow: 'reject', onDrop });

      buffer.offer('a');
      buffer.offer('b');
      buffer.offer('c');
      buffer.clear();

      expect(onDrop).toHaveBeenCalledTimes(3);
      expect(onDrop.mock.calls.map(([value]) => value)).toEqual(['a', 'b', 'c']);
      expect(buffer.size).toBe(0);

      buffer.clear();
      expect(onDrop).toHaveBeenCalledTimes(3);
    });

    it('does not fire onDrop for values handed to the consumer via take()', () => {
      const onDrop = vi.fn();
      const buffer = createBoundedBuffer<string>({ capacity: 2, overflow: 'reject', onDrop });

      buffer.offer('a');
      expect(buffer.take()).toBe('a');
      buffer.clear();

      expect(onDrop).not.toHaveBeenCalled();
    });
  });

  describe('throwing onDrop hook', () => {
    afterEach(() => {
      setRootLogger(noopLogger);
    });

    it('clear() still drains every value and logs instead of throwing', () => {
      const { logger, calls } = createStubLogger();
      setRootLogger(logger);
      const dropped: string[] = [];
      const buffer = createBoundedBuffer<string>({
        capacity: 3,
        overflow: 'reject',
        onDrop: (value) => {
          dropped.push(value);
          throw new Error('drop boom');
        },
      });
      buffer.offer('a');
      buffer.offer('b');
      buffer.offer('c');

      expect(() => buffer.clear()).not.toThrow();

      expect(dropped).toEqual(['a', 'b', 'c']);
      expect(buffer.size).toBe(0);
      expect(calls.filter((call) => call.level === 'warn')).toHaveLength(3);
    });

    it('drop-oldest eviction keeps buffer invariants and reports the eviction to the caller', () => {
      const { logger, calls } = createStubLogger();
      setRootLogger(logger);
      const buffer = createBoundedBuffer<string>({
        capacity: 1,
        overflow: 'drop-oldest',
        onDrop: () => {
          throw new Error('drop boom');
        },
      });
      buffer.offer('a');

      expect(buffer.offer('b')).toEqual({ kind: 'accepted', dropped: 'a' });
      expect(buffer.toArray()).toEqual(['b']);
      expect(calls.filter((call) => call.level === 'warn')).toHaveLength(1);
    });

    it('drop-newest policy drop reports the drop to the caller despite the throw', () => {
      const { logger, calls } = createStubLogger();
      setRootLogger(logger);
      const buffer = createBoundedBuffer<string>({
        capacity: 1,
        overflow: 'drop-newest',
        onDrop: () => {
          throw new Error('drop boom');
        },
      });
      buffer.offer('a');

      expect(buffer.offer('b')).toEqual({ kind: 'dropped', value: 'b' });
      expect(buffer.toArray()).toEqual(['a']);
      expect(calls.filter((call) => call.level === 'warn')).toHaveLength(1);
    });
  });

  describe('offer(undefined)', () => {
    it('throws with a clear message', () => {
      const buffer = createBoundedBuffer<string | undefined>({ capacity: 2, overflow: 'reject' });

      expect(() => buffer.offer(undefined)).toThrow(/undefined/);
      expect(buffer.size).toBe(0);
    });
  });
});
