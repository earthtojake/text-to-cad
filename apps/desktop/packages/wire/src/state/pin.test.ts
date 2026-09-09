import { createScope } from '@emdash/shared/concurrency';
import { createManualClock } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { cell, flushStateTurn } from './core';
import { pin, prefetch } from './pin';

describe('state pin', () => {
  it('aggregates loading status and resolves when all nodes settle', async () => {
    const scope = createScope();
    const first = cell<string | undefined>(undefined);
    const second = cell('ready');
    first.set(undefined, { status: 'loading', notify: false });

    const pins = pin(scope, [first, second]);
    const settled = pins.settled();
    let didSettle = false;
    void settled.then(() => {
      didSettle = true;
    });

    expect(pins.status).toBe('loading');
    first.set('ready');
    flushStateTurn();
    await settled;

    expect(didSettle).toBe(true);
    expect(pins.status).toBe('live');
    await scope.dispose();
  });

  it('reports the weakest status across pinned nodes', async () => {
    const scope = createScope();
    const live = cell('live');
    const failing = cell<string | undefined>(undefined);
    failing.set(undefined, { status: 'error', error: new Error('failed'), notify: false });

    const pins = pin(scope, [live, failing]);

    expect(pins.status).toBe('error');
    await expect(pins.settled()).resolves.toBeUndefined();
    await scope.dispose();
  });

  it('prefetch retains demand until its ttl expires', async () => {
    const clock = createManualClock();
    const observed: boolean[] = [];
    const model = cell('value', {
      onObservedChange: (value) => observed.push(value),
    });

    prefetch(model, { ttlMs: 10, clock });
    expect(observed).toEqual([true]);

    await clock.advanceBy(10);
    expect(observed).toEqual([true, false]);
  });
});
