import { describe, expect, it, vi } from 'vitest';
import { createLineLogStore } from './line-store';

/** Manual flush scheduler: collects scheduled flushes and runs them on demand. */
function manualScheduler() {
  const pending: Array<() => void> = [];
  return {
    schedule: (flush: () => void) => {
      pending.push(flush);
    },
    runAll() {
      for (const flush of pending.splice(0)) flush();
    },
    get scheduledCount() {
      return pending.length;
    },
  };
}

function makeStore(options: { maxBufferBytes?: number; maxLineLength?: number } = {}) {
  const scheduler = manualScheduler();
  const store = createLineLogStore({ ...options, scheduleFlush: scheduler.schedule });
  return { store, scheduler };
}

describe('createLineLogStore append/line structure', () => {
  it('splits appended chunks into lines incrementally', () => {
    const { store, scheduler } = makeStore();
    store.append('hello wor');
    store.append('ld\nsecond line\npar');
    store.append('tial');
    scheduler.runAll();

    expect(store.lines()).toEqual(['hello world', 'second line', 'partial']);
  });

  it('continues a partial line across chunk boundaries and strips CRLF', () => {
    const { store, scheduler } = makeStore();
    store.append('line one\r');
    store.append('\nline two\r\n');
    scheduler.runAll();

    expect(store.lines()).toEqual(['line one', 'line two', '']);
    expect(store.text()).toBe('line one\nline two\n');
  });

  it('hard-wraps lines longer than the max line length', () => {
    const { store, scheduler } = makeStore({ maxLineLength: 10 });
    store.append('x'.repeat(25));
    scheduler.runAll();

    expect(store.lines()).toEqual(['x'.repeat(10), 'x'.repeat(10), 'x'.repeat(5)]);
  });
});

describe('createLineLogStore byte cap', () => {
  it('evicts whole oldest lines once retained bytes exceed the cap and flags truncation', () => {
    const { store, scheduler } = makeStore({ maxBufferBytes: 100 });
    for (let i = 0; i < 20; i += 1) {
      store.append(`${String(i).padStart(2, '0')}-${'x'.repeat(17)}\n`);
    }
    scheduler.runAll();

    expect(store.truncated()).toBe(true);
    const lines = store.lines().filter((line) => line.length > 0);
    expect(lines.length).toBeLessThan(20);
    // Newest lines survive; oldest are gone.
    expect(lines.at(-1)).toContain('19-');
    expect(lines[0]).not.toContain('00-');
  });

  it('reports truncation from the source snapshot', () => {
    const { store } = makeStore();
    store.reset({ baseOffset: 128, text: 'tail text', truncated: true });

    expect(store.truncated()).toBe(true);
    expect(store.lines()).toEqual(['tail text']);
  });
});

describe('createLineLogStore flush coalescing', () => {
  it('notifies subscribers at most once per scheduled flush under burst appends', () => {
    const { store, scheduler } = makeStore();
    const listener = vi.fn();
    store.onFlush(listener);

    for (let i = 0; i < 50; i += 1) store.append(`chunk-${i}\n`);
    expect(listener).not.toHaveBeenCalled();
    expect(scheduler.scheduledCount).toBe(1);

    scheduler.runAll();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(store.lines()).toHaveLength(51);

    store.append('after\n');
    scheduler.runAll();
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it('bumps the version on each flush that changed state', () => {
    const { store, scheduler } = makeStore();
    const initial = store.version();
    store.append('a');
    store.append('b');
    scheduler.runAll();
    expect(store.version()).toBe(initial + 1);
  });

  it('reset applies immediately, clears pending appends, and notifies', () => {
    const { store, scheduler } = makeStore();
    const listener = vi.fn();
    store.onFlush(listener);
    store.append('will be dropped');
    store.reset({ baseOffset: 0, text: 'fresh\nstate', truncated: false });

    expect(listener).toHaveBeenCalledTimes(1);
    expect(store.lines()).toEqual(['fresh', 'state']);

    scheduler.runAll();
    expect(store.lines()).toEqual(['fresh', 'state']);
  });
});

describe('createLineLogStore text compatibility', () => {
  it('text() flushes pending appends and joins lines', () => {
    const { store } = makeStore();
    store.append('one\ntwo');
    expect(store.text()).toBe('one\ntwo');
  });
});
