/**
 * createFrameScheduler — unit tests.
 *
 * Uses a fake rAF (synchronous callback queue) so no real timers are needed.
 * Tests cover:
 * - demand-driven: starts idle, runs only when request() is called.
 * - read runs before write per frame.
 * - sleeps when all phases return false / void.
 * - re-schedules while animate or write returns true.
 * - dispose() cancels a pending frame.
 */

import { describe, expect, it, vi } from 'vitest';
import { createFrameScheduler } from './frame-scheduler';

// ── Fake rAF ──────────────────────────────────────────────────────────────────

function makeFakeRaf() {
  let nextId = 1;
  const pending = new Map<number, FrameRequestCallback>();

  const requestAnimationFrame = (cb: FrameRequestCallback): number => {
    const id = nextId++;
    pending.set(id, cb);
    return id;
  };

  const cancelAnimationFrame = (id: number): void => {
    pending.delete(id);
  };

  const flush = (now = 0) => {
    const callbacks = [...pending.values()];
    pending.clear();
    for (const cb of callbacks) cb(now);
  };

  const queueLength = () => pending.size;

  return { requestAnimationFrame, cancelAnimationFrame, flush, queueLength };
}

// Patch global rAF/cAF for the duration of a test.
function withFakeRaf<T>(raf: ReturnType<typeof makeFakeRaf>, fn: () => T): T {
  const origReq = globalThis.requestAnimationFrame;
  const origCan = globalThis.cancelAnimationFrame;
  globalThis.requestAnimationFrame = raf.requestAnimationFrame;
  globalThis.cancelAnimationFrame = raf.cancelAnimationFrame;
  try {
    return fn();
  } finally {
    globalThis.requestAnimationFrame = origReq;
    globalThis.cancelAnimationFrame = origCan;
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('createFrameScheduler — demand-driven', () => {
  it('starts idle; no rAF is queued until request() is called', () => {
    const raf = makeFakeRaf();
    withFakeRaf(raf, () => {
      createFrameScheduler({
        read: vi.fn(),
        animate: vi.fn(() => false),
        write: vi.fn(() => false),
      });
      expect(raf.queueLength()).toBe(0);
    });
  });

  it('queues exactly one rAF after request()', () => {
    const raf = makeFakeRaf();
    withFakeRaf(raf, () => {
      const scheduler = createFrameScheduler({
        read: vi.fn(),
        animate: vi.fn(() => false),
        write: vi.fn(() => false),
      });
      scheduler.request();
      expect(raf.queueLength()).toBe(1);
      scheduler.dispose();
    });
  });

  it('is idempotent: multiple request() calls queue only one rAF', () => {
    const raf = makeFakeRaf();
    withFakeRaf(raf, () => {
      const scheduler = createFrameScheduler({
        read: vi.fn(),
        animate: vi.fn(() => false),
        write: vi.fn(() => false),
      });
      scheduler.request();
      scheduler.request();
      scheduler.request();
      expect(raf.queueLength()).toBe(1);
      scheduler.dispose();
    });
  });
});

describe('createFrameScheduler — read runs before write', () => {
  it('calls read, then animate, then write in each tick', () => {
    const raf = makeFakeRaf();
    withFakeRaf(raf, () => {
      const order: string[] = [];
      const scheduler = createFrameScheduler({
        read: () => {
          order.push('read');
        },
        animate: () => {
          order.push('animate');
          return false;
        },
        write: () => {
          order.push('write');
          return false;
        },
      });

      scheduler.request();
      raf.flush();

      expect(order).toEqual(['read', 'animate', 'write']);
    });
  });
});

describe('createFrameScheduler — sleeps when idle', () => {
  it('does not re-schedule when all phases return false', () => {
    const raf = makeFakeRaf();
    withFakeRaf(raf, () => {
      const scheduler = createFrameScheduler({
        read: vi.fn(),
        animate: vi.fn(() => false),
        write: vi.fn(() => false),
      });

      scheduler.request();
      expect(raf.queueLength()).toBe(1);

      raf.flush(); // tick runs; no more work
      expect(raf.queueLength()).toBe(0); // scheduler is sleeping
    });
  });

  it('re-schedules while animate returns true', () => {
    const raf = makeFakeRaf();
    withFakeRaf(raf, () => {
      let ticks = 0;
      const scheduler = createFrameScheduler({
        read: vi.fn(),
        animate: () => {
          ticks++;
          return ticks < 3;
        }, // active for 3 ticks
        write: vi.fn(() => false),
      });

      scheduler.request();
      raf.flush(); // tick 1 — animate returns true → re-schedules
      expect(raf.queueLength()).toBe(1);
      raf.flush(); // tick 2 — animate returns true → re-schedules
      expect(raf.queueLength()).toBe(1);
      raf.flush(); // tick 3 — animate returns false → sleeps
      expect(raf.queueLength()).toBe(0);

      expect(ticks).toBe(3);
    });
  });

  it('re-schedules while write returns true', () => {
    const raf = makeFakeRaf();
    withFakeRaf(raf, () => {
      let writes = 0;
      const scheduler = createFrameScheduler({
        read: vi.fn(),
        animate: vi.fn(() => false),
        write: () => {
          writes++;
          return writes < 2;
        }, // active for 2 ticks
      });

      scheduler.request();
      raf.flush(); // write returns true → re-schedules
      expect(raf.queueLength()).toBe(1);
      raf.flush(); // write returns false → sleeps
      expect(raf.queueLength()).toBe(0);
    });
  });
});

describe('createFrameScheduler — dispose', () => {
  it('cancels a pending rAF and prevents the tick from running', () => {
    const raf = makeFakeRaf();
    withFakeRaf(raf, () => {
      const read = vi.fn();
      const scheduler = createFrameScheduler({
        read,
        animate: vi.fn(() => false),
        write: vi.fn(() => false),
      });

      scheduler.request();
      expect(raf.queueLength()).toBe(1);

      scheduler.dispose();
      expect(raf.queueLength()).toBe(0);

      // Flushing after dispose should not run the tick.
      raf.flush();
      expect(read).not.toHaveBeenCalled();
    });
  });
});
