import { createScope } from '@emdash/shared/concurrency';
import { describe, expect, it } from 'vitest';
import { recordSnapshots } from '../testing';
import { batch, cell, derived, flushStateTurn, observe, peek, revisionOf, snapshot } from './index';

describe('state kernel', () => {
  it('publishes a diamond derived graph once per turn without glitches', async () => {
    const source = cell(1);
    const left = derived(() => snapshot(source).value + 1);
    const right = derived(() => snapshot(source).value * 2);
    const total = derived(() => (snapshot(left).value ?? 0) + (snapshot(right).value ?? 0));
    const recorded = recordSnapshots(total);

    source.set(2);
    flushStateTurn();

    expect(recorded.snapshots.map((current) => current.value)).toEqual([4, 7]);
    await recorded.dispose();
  });

  it('tracks dynamic dependencies and ignores dependencies that are no longer read', async () => {
    const useLeft = cell(true);
    const left = cell('left');
    const right = cell('right');
    const selected = derived(() =>
      snapshot(useLeft).value ? snapshot(left).value : snapshot(right).value
    );
    const recorded = recordSnapshots(selected);

    useLeft.set(false);
    flushStateTurn();
    left.set('ignored');
    flushStateTurn();
    right.set('updated');
    flushStateTurn();

    expect(recorded.snapshots.map((current) => current.value)).toEqual([
      'left',
      'right',
      'updated',
    ]);
    await recorded.dispose();
  });

  it('keeps dependencies from a failed first compute and retries when they publish', async () => {
    const input = cell(1);
    let shouldThrow = true;
    const computed = derived(() => {
      const value = snapshot(input).value;
      if (shouldThrow) throw new Error('boom');
      return value * 2;
    });
    const recorded = recordSnapshots(computed);

    expect(snapshot(computed).status).toBe('error');
    shouldThrow = false;
    input.set(2);
    flushStateTurn();

    expect(recorded.snapshots.map((current) => current.status)).toEqual(['error', 'live']);
    expect(snapshot(computed).value).toBe(4);
    await recorded.dispose();
  });

  it('isolates observer failures so later notifications can still flush', async () => {
    const scope = createScope();
    const errors: unknown[] = [];
    const first = cell(0, {
      instrumentation: {
        observerError: (error) => errors.push(error),
      },
    });
    const second = cell(0);
    const seen: number[] = [];

    observe(
      first,
      () => {
        throw new Error('observer failed');
      },
      { scope }
    );
    observe(second, (current) => seen.push(current.value), { scope });

    first.set(1);
    second.set(1);
    flushStateTurn();
    second.set(2);
    flushStateTurn();

    expect(errors).toHaveLength(2);
    expect(seen).toEqual([0, 1, 2]);
    await scope.dispose();
  });

  it('folds mutation ids through derived state only for dependencies that advanced', async () => {
    const source = cell(1);
    const unrelated = cell(1);
    const view = derived(() => snapshot(source).value + snapshot(unrelated).value);
    const recorded = recordSnapshots(view);

    source.set(2, { mutationIds: ['m1'] });
    flushStateTurn();
    unrelated.set(2);
    flushStateTurn();

    expect(recorded.snapshots.map((current) => current.mutationIds)).toEqual([
      undefined,
      ['m1'],
      undefined,
    ]);
    await recorded.dispose();
  });

  it('merges batch metadata and keeps peek untracked', async () => {
    const tracked = cell(1);
    const untracked = cell(10);
    const view = derived(() => snapshot(tracked).value + peek(untracked));
    const recorded = recordSnapshots(view);

    batch(
      () => {
        tracked.set(2, { mutationIds: ['inner'] });
        untracked.set(20);
      },
      { mutationIds: ['outer'] }
    );
    flushStateTurn();
    untracked.set(30);
    flushStateTurn();

    expect(recorded.snapshots.map((current) => current.value)).toEqual([11, 22]);
    expect(recorded.snapshots.at(-1)?.mutationIds).toEqual(['outer', 'inner']);
    await recorded.dispose();
  });

  it('returns the current revision without publishing', () => {
    const source = cell(1);

    const initial = revisionOf(source);
    const committed = source.set(2, { mutationIds: ['m1'] });
    const current = revisionOf(source);

    expect(initial.revision).toBe(0);
    expect(current).toEqual(committed);
    expect(snapshot(source).revision).toBe(committed.revision);
  });

  it('detaches an unobserved dependent-less derived and re-attaches lazily on read', async () => {
    const recomputes: Array<string | undefined> = [];
    const source = cell(1);
    const view = derived(() => snapshot(source).value * 2, {
      name: 'detachable',
      instrumentation: { nodeRecomputed: (name) => recomputes.push(name) },
    });
    const scope = createScope();
    observe(view, () => {}, { scope });
    flushStateTurn();
    expect(snapshot(view).value).toBe(2);

    await scope.dispose();
    const recomputesAfterDetach = recomputes.length;

    // Detached: dependency writes no longer reach the derived.
    source.set(2);
    flushStateTurn();
    expect(recomputes.length).toBe(recomputesAfterDetach);

    // Lazy re-attach: the next read recomputes with the fresh dependency value.
    expect(snapshot(view).value).toBe(4);
    expect(recomputes.length).toBe(recomputesAfterDetach + 1);

    // Re-attached: observing again tracks further writes.
    const seen: Array<number | undefined> = [];
    const reobserved = createScope();
    observe(view, (current) => seen.push(current.value), { scope: reobserved });
    source.set(5);
    flushStateTurn();
    expect(seen.at(-1)).toBe(10);
    await reobserved.dispose();
  });

  it('cascades detach through a chain of unobserved deriveds and stays correct', async () => {
    const source = cell(1);
    const middle = derived(() => snapshot(source).value + 1);
    const top = derived(() => (snapshot(middle).value ?? 0) * 10);
    const scope = createScope();
    observe(top, () => {}, { scope });
    flushStateTurn();
    expect(snapshot(top).value).toBe(20);

    await scope.dispose();
    source.set(5);
    flushStateTurn();

    expect(snapshot(top).value).toBe(60);
    expect(snapshot(middle).value).toBe(6);
  });
});
