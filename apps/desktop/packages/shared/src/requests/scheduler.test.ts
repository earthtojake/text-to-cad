import { describe, expect, it } from 'vitest';
import { createScope } from '../concurrency';
import { deferred } from '../testing';
import type { RateGate } from './rate-gate';
import { createRequestScheduler } from './scheduler';

describe('createRequestScheduler', () => {
  it('runs higher priorities first and preserves FIFO within a priority', async () => {
    const scope = createScope({ label: 'scheduler-test' });
    const scheduler = createRequestScheduler({ scope, maxConcurrency: 1 });
    const firstGate = deferred<void>();
    const firstStarted = deferred<void>();
    const order: string[] = [];
    const first = scheduler.submit({
      priority: 0,
      async run() {
        firstStarted.resolve();
        await firstGate.promise;
        order.push('first');
      },
    });
    await firstStarted.promise;
    const background = scheduler.submit({
      priority: 0,
      async run() {
        order.push('background');
      },
    });
    const interactiveOne = scheduler.submit({
      priority: 2,
      async run() {
        order.push('interactive-1');
      },
    });
    const task = scheduler.submit({
      priority: 1,
      async run() {
        order.push('task');
      },
    });
    const interactiveTwo = scheduler.submit({
      priority: 2,
      async run() {
        order.push('interactive-2');
      },
    });

    firstGate.resolve();
    await Promise.all([first, background, interactiveOne, task, interactiveTwo]);

    expect(order).toEqual(['first', 'interactive-1', 'interactive-2', 'task', 'background']);
    await scheduler.dispose();
    await scope.dispose();
  });

  it('deduplicates keyed work and promotes queued priority', async () => {
    const scope = createScope({ label: 'scheduler-test' });
    const scheduler = createRequestScheduler({ scope, maxConcurrency: 1 });
    const blocker = deferred<void>();
    const blockerStarted = deferred<void>();
    const events: string[] = [];
    const first = scheduler.submit({
      priority: 0,
      async run() {
        blockerStarted.resolve();
        await blocker.promise;
      },
    });
    await blockerStarted.promise;
    let calls = 0;
    const low = scheduler.submit({
      key: 'shared',
      priority: 0,
      async run() {
        calls += 1;
        events.push('shared');
        return 42;
      },
    });
    const other = scheduler.submit({
      priority: 1,
      async run() {
        events.push('other');
      },
    });
    const high = scheduler.submit({
      key: 'shared',
      priority: 2,
      async run() {
        throw new Error('duplicate implementation must not run');
      },
    });

    blocker.resolve();
    await first;
    await expect(Promise.all([low, high])).resolves.toEqual([42, 42]);
    await other;

    expect(calls).toBe(1);
    expect(events).toEqual(['shared', 'other']);
    await scheduler.dispose();
    await scope.dispose();
  });

  it('deduplicates empty-string keys', async () => {
    const scope = createScope({ label: 'scheduler-test' });
    const scheduler = createRequestScheduler({ scope, maxConcurrency: 2 });
    const release = deferred<void>();
    let calls = 0;
    const request = {
      key: '',
      priority: 0,
      async run() {
        calls += 1;
        await release.promise;
        return 'ok';
      },
    };

    const first = scheduler.submit(request);
    const second = scheduler.submit(request);
    while (calls === 0) await Promise.resolve();
    expect(calls).toBe(1);
    release.resolve();
    await expect(Promise.all([first, second])).resolves.toEqual(['ok', 'ok']);
    await scheduler.dispose();
    await scope.dispose();
  });

  it('does not attach new callers to canceled keyed work', async () => {
    const scope = createScope({ label: 'scheduler-test' });
    const scheduler = createRequestScheduler({ scope, maxConcurrency: 2 });
    const started = deferred<void>();
    const finishCancellation = deferred<void>();
    const abort = new AbortController();
    const first = scheduler.submit(
      {
        key: 'shared',
        priority: 0,
        async run(signal) {
          started.resolve();
          await new Promise<void>((resolve) => {
            signal.addEventListener('abort', () => resolve(), { once: true });
          });
          await finishCancellation.promise;
          throw signal.reason;
        },
      },
      { signal: abort.signal }
    );
    await started.promise;

    abort.abort(new Error('first cancelled'));
    await expect(first).rejects.toThrow('first cancelled');
    const second = scheduler.submit({
      key: 'shared',
      priority: 2,
      async run() {
        return 'fresh';
      },
    });

    await expect(second).resolves.toBe('fresh');
    finishCancellation.resolve();
    await scheduler.dispose();
    await scope.dispose();
  });

  it('waits for the gate before consuming concurrency slots', async () => {
    const scope = createScope({ label: 'scheduler-test' });
    const gateStarted = deferred<void>();
    const gateRelease = deferred<void>();
    let acquisitions = 0;
    const gate: RateGate = {
      async acquire() {
        acquisitions += 1;
        if (acquisitions === 1) {
          gateStarted.resolve();
          await gateRelease.promise;
        }
      },
      observe() {},
    };
    const scheduler = createRequestScheduler({ scope, maxConcurrency: 3, gate });
    const order: string[] = [];
    const first = scheduler.submit({
      priority: 0,
      async run() {
        order.push('first-background');
      },
    });
    await gateStarted.promise;
    const background = scheduler.submit({
      priority: 0,
      async run() {
        order.push('second-background');
      },
    });
    const interactive = scheduler.submit({
      priority: 2,
      async run() {
        order.push('interactive');
      },
    });

    expect(scheduler.stats.inFlight).toBe(0);
    gateRelease.resolve();
    await Promise.all([first, background, interactive]);
    expect(order).toEqual(['first-background', 'interactive', 'second-background']);
    await scheduler.dispose();
    await scope.dispose();
  });

  it('removes an aborted queued request', async () => {
    const scope = createScope({ label: 'scheduler-test' });
    const scheduler = createRequestScheduler({ scope, maxConcurrency: 1 });
    const blocker = deferred<void>();
    const blockerStarted = deferred<void>();
    const first = scheduler.submit({
      priority: 0,
      async run() {
        blockerStarted.resolve();
        await blocker.promise;
      },
    });
    await blockerStarted.promise;
    const abort = new AbortController();
    let ran = false;
    const queued = scheduler.submit(
      {
        priority: 1,
        async run() {
          ran = true;
        },
      },
      { signal: abort.signal }
    );

    abort.abort(new Error('cancelled'));
    await expect(queued).rejects.toThrow('cancelled');
    blocker.resolve();
    await first;
    await Promise.resolve();
    expect(ran).toBe(false);
    expect(scheduler.stats.pending).toBe(0);
    await scheduler.dispose();
    await scope.dispose();
  });

  it('cancels in-flight work when disposed', async () => {
    const scope = createScope({ label: 'scheduler-test' });
    const scheduler = createRequestScheduler({ scope, maxConcurrency: 1 });
    const started = deferred<void>();
    const pending = scheduler.submit({
      priority: 0,
      async run(signal) {
        started.resolve();
        await new Promise<never>((_resolve, reject) => {
          signal.addEventListener('abort', () => reject(signal.reason), { once: true });
        });
      },
    });
    await started.promise;

    await scheduler.dispose();

    await expect(pending).rejects.toThrow('Request scheduler disposed');
    await scope.dispose();
  });

  it('bounds concurrent execution', async () => {
    const scope = createScope({ label: 'scheduler-test' });
    const scheduler = createRequestScheduler({ scope, maxConcurrency: 2 });
    const gate = deferred<void>();
    let active = 0;
    let maxActive = 0;
    const requests = Array.from({ length: 4 }, (_, index) =>
      scheduler.submit({
        priority: 0,
        async run() {
          active += 1;
          maxActive = Math.max(maxActive, active);
          await gate.promise;
          active -= 1;
          return index;
        },
      })
    );

    while (maxActive < 2) await Promise.resolve();
    expect(maxActive).toBe(2);
    gate.resolve();
    await expect(Promise.all(requests)).resolves.toEqual([0, 1, 2, 3]);
    expect(maxActive).toBe(2);
    await scheduler.dispose();
    await scope.dispose();
  });
});
