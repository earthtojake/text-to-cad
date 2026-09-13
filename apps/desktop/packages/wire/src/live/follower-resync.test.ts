import { retrySchedule } from '@emdash/shared/scheduling';
import { createManualClock } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import type { LiveSnapshot, LiveUpdate } from '../api/channel';
import type { WireResyncFailedEvent } from '../api/instrumentation';
import { resyncMarkStale, resyncRetry } from './follower';
import { LiveJobClient } from './job';
import { liveJobStateSchema } from './protocol';
import { LiveStateClient } from './state';

const stateSchema = z.object({ count: z.number() });
type State = z.infer<typeof stateSchema>;

function snapshotOf(count: number, generation: number, sequence: number): LiveSnapshot<State> {
  return { generation, sequence, timestamp: 0, data: { count } };
}

function updateOf(
  generation: number,
  baseSequence: number,
  count: number,
  mutationIds: string[] = []
): LiveUpdate {
  return {
    generation,
    baseSequence,
    sequence: baseSequence + 1,
    timestamp: 0,
    delta: [{ op: 'replace', path: ['count'], value: count }],
    mutationIds,
  };
}

describe('follower resync failure policy', () => {
  it('retries a failed resync on the schedule until it succeeds', async () => {
    const clock = createManualClock();
    const failures: WireResyncFailedEvent[] = [];
    let refetches = 0;
    const client = new LiveStateClient<State>(
      stateSchema,
      async () => {
        refetches += 1;
        if (refetches < 3) throw new Error(`refetch failure ${refetches}`);
        return snapshotOf(7, 2, 0);
      },
      () => {},
      {
        clock,
        onResyncFailed: resyncRetry({
          schedule: retrySchedule({ delaysMs: [100, 200], repeatLast: true }),
        }),
        instrumentation: { resyncFailed: (event) => failures.push(event) },
      }
    );
    client.seed(snapshotOf(0, 1, 0));

    // A generation bump forces a resync; the first two refetches fail.
    client.applyUpdate(updateOf(2, 0, 1));
    await clock.advanceBy(0);
    expect(refetches).toBe(1);
    expect(client.stale).toBe(true);

    await clock.advanceBy(100);
    expect(refetches).toBe(2);
    expect(client.stale).toBe(true);

    await clock.advanceBy(200);
    expect(refetches).toBe(3);
    expect(client.stale).toBe(false);
    expect(client.getSnapshot()).toEqual({ count: 7 });
    expect(failures).toMatchObject([
      { attempt: 1, willRetry: true },
      { attempt: 2, willRetry: true },
    ]);
  });

  it('marks the follower stale on give-up and recovers on the next update', async () => {
    const clock = createManualClock();
    const failures: WireResyncFailedEvent[] = [];
    let failRefetch = true;
    let refetches = 0;
    const client = new LiveStateClient<State>(
      stateSchema,
      async () => {
        refetches += 1;
        if (failRefetch) throw new Error('refetch failure');
        return snapshotOf(9, 3, 0);
      },
      () => {},
      {
        clock,
        onResyncFailed: resyncMarkStale(),
        instrumentation: { resyncFailed: (event) => failures.push(event) },
      }
    );
    client.seed(snapshotOf(0, 1, 0));

    client.applyUpdate(updateOf(2, 0, 1));
    await clock.advanceBy(0);
    expect(refetches).toBe(1);
    expect(client.stale).toBe(true);
    expect(client.getSnapshot()).toEqual({ count: 0 });
    expect(failures).toMatchObject([{ attempt: 1, willRetry: false }]);

    // The next update re-triggers a fresh resync episode, which now succeeds.
    failRefetch = false;
    client.applyUpdate(updateOf(3, 5, 1));
    await clock.advanceBy(0);
    expect(refetches).toBe(2);
    expect(client.stale).toBe(false);
    expect(client.getSnapshot()).toEqual({ count: 9 });
  });

  it('rejects refresh() when the policy gives up', async () => {
    const clock = createManualClock();
    const client = new LiveStateClient<State>(
      stateSchema,
      async () => {
        throw new Error('permanently unreachable');
      },
      () => {},
      { clock, onResyncFailed: resyncMarkStale() }
    );
    client.seed(snapshotOf(0, 1, 0));

    await expect(client.refresh()).rejects.toThrow('permanently unreachable');
    expect(client.stale).toBe(true);
  });

  it('coalesces concurrent refresh() calls onto one resync', async () => {
    const clock = createManualClock();
    let refetches = 0;
    let release: (snapshot: LiveSnapshot<State>) => void = () => {};
    const client = new LiveStateClient<State>(
      stateSchema,
      () => {
        refetches += 1;
        return new Promise<LiveSnapshot<State>>((resolve) => {
          release = resolve;
        });
      },
      () => {},
      { clock, onResyncFailed: resyncRetry() }
    );
    client.seed(snapshotOf(0, 1, 0));

    const first = client.refresh();
    const second = client.refresh();
    await clock.advanceBy(0);
    release(snapshotOf(5, 2, 0));
    await expect(first).resolves.toBeUndefined();
    await expect(second).resolves.toBeUndefined();
    expect(refetches).toBe(1);
    expect(client.getSnapshot()).toEqual({ count: 5 });
  });

  it('re-runs the resync loop when a trigger arrives mid-reseed', async () => {
    const clock = createManualClock();
    const snapshots: Array<LiveSnapshot<State>> = [snapshotOf(1, 2, 0), snapshotOf(2, 3, 0)];
    const releases: Array<(snapshot: LiveSnapshot<State>) => void> = [];
    const client = new LiveStateClient<State>(
      stateSchema,
      () =>
        new Promise<LiveSnapshot<State>>((resolve) => {
          releases.push(resolve);
        }),
      () => {},
      { clock, onResyncFailed: resyncRetry() }
    );
    client.seed(snapshotOf(0, 1, 0));

    const refresh = client.refresh();
    let resolved = false;
    void refresh.then(() => {
      resolved = true;
    });
    await clock.advanceBy(0);
    expect(releases).toHaveLength(1);

    // A generation bump lands while the first reseed is still in flight.
    client.applyUpdate(updateOf(3, 0, 1));
    releases[0](snapshots[0]);
    await clock.advanceBy(0);

    // refresh() must not resolve on the now-stale seed; the loop re-runs.
    expect(resolved).toBe(false);
    expect(releases).toHaveLength(2);
    releases[1](snapshots[1]);
    await expect(refresh).resolves.toBeUndefined();
    expect(client.getSnapshot()).toEqual({ count: 2 });
    expect(client.stale).toBe(false);
  });

  it('rejects pending refresh and waiters on dispose, including wait-forever waiters', async () => {
    const clock = createManualClock();
    const client = new LiveStateClient<State>(
      stateSchema,
      () => new Promise<LiveSnapshot<State>>(() => {}),
      () => {},
      { clock, onResyncFailed: resyncRetry() }
    );
    client.seed(snapshotOf(0, 1, 0));

    const refresh = client.refresh();
    const cursorWait = client.waitForCursor({ generation: 1, sequence: 10 }, 0);
    const mutationWait = client.waitForMutation('m1', 0);

    client.dispose();

    await expect(refresh).rejects.toThrow('disposed');
    await expect(cursorWait).rejects.toThrow('disposed');
    await expect(mutationWait).rejects.toThrow('disposed');
    await expect(client.refresh()).rejects.toThrow('disposed');
    await expect(client.waitForCursor({ generation: 1, sequence: 10 })).rejects.toThrow('disposed');
  });

  it('stops a retry loop on dispose', async () => {
    const clock = createManualClock();
    let refetches = 0;
    const client = new LiveStateClient<State>(
      stateSchema,
      async () => {
        refetches += 1;
        throw new Error('refetch failure');
      },
      () => {},
      {
        clock,
        onResyncFailed: resyncRetry({
          schedule: retrySchedule({ delaysMs: [50], repeatLast: true }),
        }),
      }
    );
    client.seed(snapshotOf(0, 1, 0));

    client.invalidate();
    await clock.advanceBy(0);
    expect(refetches).toBe(1);

    client.dispose();
    await clock.advanceBy(1_000);
    expect(refetches).toBe(1);
  });

  it('rejects pending job waiters on dispose', async () => {
    const clock = createManualClock();
    const progressSchema = z.object({ step: z.number() });
    const resultSchema = z.object({ ok: z.boolean() });
    const errorSchema = z.object({ message: z.string() });
    const jobSchema = liveJobStateSchema(progressSchema, resultSchema, errorSchema);
    const client = new LiveJobClient(jobSchema, {
      refetchSnapshot: async () => {
        throw new Error('unused');
      },
      onResyncFailed: resyncMarkStale(),
      clock,
    });
    client.seed({
      generation: 1,
      sequence: 0,
      timestamp: 0,
      data: { status: 'running', startedAt: 0, progress: [], progressCount: 0 },
    });

    const terminal = client.waitForTerminal(0);
    const progress = client.waitForProgressCount(3, 0);

    client.dispose();

    await expect(terminal).rejects.toThrow('disposed');
    await expect(progress).rejects.toThrow('disposed');
    await expect(client.waitForTerminal()).rejects.toThrow('disposed');
  });

  it('never leaks an unhandled rejection from internal resync triggers', async () => {
    const clock = createManualClock();
    const unhandled = vi.fn();
    process.on('unhandledRejection', unhandled);
    try {
      const client = new LiveStateClient<State>(
        stateSchema,
        async () => {
          throw new Error('refetch failure');
        },
        () => {},
        { clock, onResyncFailed: resyncMarkStale() }
      );
      client.seed(snapshotOf(0, 1, 0));

      client.applyUpdate(updateOf(9, 0, 1));
      await clock.advanceBy(0);
      client.dispose();
      await clock.advanceBy(1_000);
      await new Promise((resolve) => setImmediate(resolve));

      expect(unhandled).not.toHaveBeenCalled();
    } finally {
      process.off('unhandledRejection', unhandled);
    }
  });
});
