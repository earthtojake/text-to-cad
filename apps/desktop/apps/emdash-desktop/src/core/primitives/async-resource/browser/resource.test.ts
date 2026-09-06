import { createManualClock } from '@emdash/shared/testing';
import { autorun } from 'mobx';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Resource } from './resource';

/** Macrotask boundary: drains all pending microtasks (load promise chains). */
const settle = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

/** Minimal document stand-in for pauseWhenHidden in the node test environment. */
function stubDocumentVisibility() {
  let hidden = false;
  const listeners = new Set<() => void>();
  vi.stubGlobal('document', {
    get hidden() {
      return hidden;
    },
    addEventListener: (_type: string, listener: () => void) => {
      listeners.add(listener);
    },
    removeEventListener: (_type: string, listener: () => void) => {
      listeners.delete(listener);
    },
  });
  return {
    setHidden(value: boolean) {
      hidden = value;
      for (const listener of [...listeners]) listener();
    },
  };
}

describe('Resource', () => {
  it('queues event reloads that arrive during an in-flight load', async () => {
    let fetchCount = 0;
    let releaseFirst: (() => void) | undefined;
    let secondLoadComplete: (() => void) | undefined;
    let emitReload: (() => void) | undefined;
    const secondLoad = new Promise<void>((resolve) => {
      secondLoadComplete = resolve;
    });

    const resource = new Resource(async () => {
      fetchCount += 1;
      if (fetchCount === 1) {
        await new Promise<void>((resolve) => {
          releaseFirst = resolve;
        });
        return 'stale';
      }
      secondLoadComplete?.();
      return 'fresh';
    }, [
      {
        kind: 'event',
        subscribe: (handler) => {
          emitReload = () => handler(undefined);
          return () => {};
        },
        onEvent: 'reload',
      },
    ]);

    resource.start();
    emitReload?.();
    releaseFirst?.();

    await secondLoad;
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(fetchCount).toBe(2);
    expect(resource.data).toBe('fresh');
  });

  it('ignores an event delivered synchronously after dispose', async () => {
    let fetchCount = 0;
    let emit: (() => void) | undefined;
    const resource = new Resource(async () => {
      fetchCount += 1;
      return fetchCount;
    }, [
      {
        kind: 'event',
        subscribe: (handler) => {
          emit = () => handler(undefined);
          return () => {};
        },
        onEvent: 'reload',
      },
    ]);

    resource.start();
    await settle();
    expect(fetchCount).toBe(1);

    // Scope cleanup runs across microtasks, so the subscription is still live
    // on the tick dispose() returns; the event must not trigger a fetch.
    resource.dispose();
    emit?.();
    await settle();

    expect(fetchCount).toBe(1);
  });

  it('runs one fresh reload after an invalidation arrives during an in-flight load', async () => {
    let fetchCount = 0;
    let releaseFirst: (() => void) | undefined;
    let secondLoadComplete: (() => void) | undefined;
    const secondLoad = new Promise<void>((resolve) => {
      secondLoadComplete = resolve;
    });

    const resource = new Resource(async () => {
      fetchCount += 1;
      if (fetchCount === 1) {
        await new Promise<void>((resolve) => {
          releaseFirst = resolve;
        });
        return 'stale';
      }
      secondLoadComplete?.();
      return 'fresh';
    }, []);

    const firstLoad = resource.load();
    resource.invalidate();
    releaseFirst?.();

    await firstLoad;
    await secondLoad;
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(fetchCount).toBe(2);
    expect(resource.data).toBe('fresh');
  });

  it('keeps loading true between an in-flight load and its queued reload', async () => {
    let fetchCount = 0;
    let releaseFirst: (() => void) | undefined;
    let releaseSecond: (() => void) | undefined;

    const resource = new Resource(async () => {
      fetchCount += 1;
      await new Promise<void>((resolve) => {
        if (fetchCount === 1) {
          releaseFirst = resolve;
        } else {
          releaseSecond = resolve;
        }
      });
      return fetchCount === 1 ? 'stale' : 'fresh';
    }, []);

    const loadingStates: boolean[] = [];
    const dispose = autorun(() => {
      loadingStates.push(resource.loading);
    });

    const firstLoad = resource.load();
    resource.invalidate();
    releaseFirst?.();
    await firstLoad;

    expect(fetchCount).toBe(2);
    expect(loadingStates).toEqual([false, true]);

    releaseSecond?.();
    await new Promise<void>((resolve) => setTimeout(resolve, 0));

    expect(resource.data).toBe('fresh');
    expect(loadingStates).toEqual([false, true, false]);
    dispose();
  });

  it('dedupes overlapping direct loads without queueing an extra reload', async () => {
    let fetchCount = 0;
    let releaseFirst: (() => void) | undefined;

    const resource = new Resource(async () => {
      fetchCount += 1;
      await new Promise<void>((resolve) => {
        releaseFirst = resolve;
      });
      return 'loaded';
    }, []);

    const firstLoad = resource.load();
    const secondLoad = resource.load();
    releaseFirst?.();

    await Promise.all([firstLoad, secondLoad]);

    expect(fetchCount).toBe(1);
    expect(resource.data).toBe('loaded');
  });

  describe('poll strategy on an injected clock', () => {
    it('runs the initial load and then one fetch per interval', async () => {
      const clock = createManualClock();
      let fetchCount = 0;
      const resource = new Resource(
        async () => {
          fetchCount += 1;
          return fetchCount;
        },
        [{ kind: 'poll', intervalMs: 1_000 }],
        { clock }
      );

      resource.start();
      await settle();
      expect(fetchCount).toBe(1);

      await clock.advanceBy(999);
      await settle();
      expect(fetchCount).toBe(1);

      await clock.advanceBy(1);
      await settle();
      expect(fetchCount).toBe(2);

      await clock.advanceBy(1_000);
      await settle();
      expect(fetchCount).toBe(3);
      expect(resource.data).toBe(3);
    });

    it('stops polling after dispose, idempotently', async () => {
      const clock = createManualClock();
      let fetchCount = 0;
      const resource = new Resource(
        async () => {
          fetchCount += 1;
          return fetchCount;
        },
        [{ kind: 'poll', intervalMs: 1_000 }],
        { clock }
      );

      resource.start();
      await settle();
      await clock.advanceBy(1_000);
      await settle();
      expect(fetchCount).toBe(2);

      resource.dispose();
      resource.dispose();
      await settle();

      await clock.advanceBy(10_000);
      await settle();
      expect(fetchCount).toBe(2);
    });

    it('stamps lastUpdatedAt from the injected clock', async () => {
      const clock = createManualClock(5_000);
      const resource = new Resource(async () => 'value', [], { clock });

      await resource.load();
      await settle();
      expect(resource.lastUpdatedAt).toBe(5_000);

      await clock.advanceBy(250);
      resource.setValue('newer');
      expect(resource.lastUpdatedAt).toBe(5_250);
    });
  });

  describe('debounced event strategy on an injected clock', () => {
    function createEventResource(debounceMs: number) {
      const clock = createManualClock();
      let fetchCount = 0;
      let emit: (() => void) | undefined;
      let unsubscribeCount = 0;
      const resource = new Resource(
        async () => {
          fetchCount += 1;
          return fetchCount;
        },
        [
          {
            kind: 'event',
            subscribe: (handler) => {
              emit = () => handler(undefined);
              return () => {
                unsubscribeCount += 1;
              };
            },
            onEvent: 'reload',
            debounceMs,
          },
        ],
        { clock }
      );
      return {
        clock,
        resource,
        emit: () => emit?.(),
        fetchCount: () => fetchCount,
        unsubscribeCount: () => unsubscribeCount,
      };
    }

    it('coalesces an event burst into one reload after the debounce window', async () => {
      const { clock, resource, emit, fetchCount } = createEventResource(100);

      resource.start();
      await settle();
      expect(fetchCount()).toBe(1);

      emit();
      emit();
      emit();
      await clock.advanceBy(99);
      await settle();
      expect(fetchCount()).toBe(1);

      await clock.advanceBy(1);
      await settle();
      expect(fetchCount()).toBe(2);
    });

    it('restarts the debounce window on each event', async () => {
      const { clock, resource, emit, fetchCount } = createEventResource(100);

      resource.start();
      await settle();

      emit();
      await clock.advanceBy(60);
      emit();
      await clock.advanceBy(60);
      await settle();
      expect(fetchCount()).toBe(1);

      await clock.advanceBy(40);
      await settle();
      expect(fetchCount()).toBe(2);
    });

    it('dispose unsubscribes once and drops a pending debounced reload', async () => {
      const { clock, resource, emit, fetchCount, unsubscribeCount } = createEventResource(100);

      resource.start();
      await settle();
      expect(fetchCount()).toBe(1);

      emit();
      resource.dispose();
      resource.dispose();
      await settle();

      await clock.advanceBy(1_000);
      await settle();
      expect(fetchCount()).toBe(1);
      expect(unsubscribeCount()).toBe(1);
    });

    it('ignores an event delivered synchronously after dispose', async () => {
      const { clock, resource, emit, fetchCount } = createEventResource(100);

      resource.start();
      await settle();
      expect(fetchCount()).toBe(1);

      resource.dispose();
      emit();
      await settle();

      await clock.advanceBy(1_000);
      await settle();
      expect(fetchCount()).toBe(1);
    });
  });

  describe('pauseWhenHidden', () => {
    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('pauses polling while hidden and resumes when visible again', async () => {
      const visibility = stubDocumentVisibility();
      const clock = createManualClock();
      let fetchCount = 0;
      const resource = new Resource(
        async () => {
          fetchCount += 1;
          return fetchCount;
        },
        [{ kind: 'poll', intervalMs: 1_000, pauseWhenHidden: true }],
        { clock }
      );

      resource.start();
      await settle();
      expect(fetchCount).toBe(1);

      await clock.advanceBy(1_000);
      await settle();
      expect(fetchCount).toBe(2);

      visibility.setHidden(true);
      await clock.advanceBy(5_000);
      await settle();
      expect(fetchCount).toBe(2);

      visibility.setHidden(false);
      await clock.advanceBy(1_000);
      await settle();
      expect(fetchCount).toBe(3);

      resource.dispose();
      await settle();
      await clock.advanceBy(5_000);
      await settle();
      expect(fetchCount).toBe(3);
    });
  });
});
