import { describe, expect, it } from 'vitest';
import { GitSchedule, isTransientLockError, retryTransientLock } from './git-schedule';

// Unit tests for the host-wide git budget (spec: workspace-lifecycle-v2, git
// concurrency model): one semaphore over every registry-spawned subprocess with
// priority classes creation > activation > background > probe, +2 headroom so the
// top tiers always start immediately, and per-repository idle gates for the lowest
// tier. Assertions are external ordering only — no queue internals.

type Gate = { release: () => void; done: Promise<void> };

function gated(
  schedule: GitSchedule,
  tier: Parameters<GitSchedule['run']>[0]['tier'],
  repository?: string
): Gate {
  let release!: () => void;
  const blocker = new Promise<void>((resolve) => {
    release = resolve;
  });
  const done = schedule.run({ tier, repository }, () => blocker);
  return { release, done };
}

async function settle(): Promise<void> {
  for (let i = 0; i < 5; i += 1) await Promise.resolve();
}

describe('GitSchedule', () => {
  it('runs tasks up to capacity and queues the rest', async () => {
    const schedule = new GitSchedule({ capacity: 2, headroom: 0 });
    const order: string[] = [];
    const first = gated(schedule, 'probe');
    const second = gated(schedule, 'probe');
    await settle();

    let thirdStarted = false;
    const third = schedule.run({ tier: 'probe' }, async () => {
      thirdStarted = true;
      order.push('third');
    });
    await settle();
    expect(thirdStarted).toBe(false);

    first.release();
    await first.done;
    await third;
    expect(thirdStarted).toBe(true);
    second.release();
    await second.done;
  });

  it('creation starts immediately through headroom when low tiers saturate the budget', async () => {
    const schedule = new GitSchedule({ capacity: 2, headroom: 2 });
    const probes = [gated(schedule, 'probe'), gated(schedule, 'probe')];
    await settle();

    // The budget is saturated by probes; a queued probe waits...
    let lateProbeStarted = false;
    const lateProbe = schedule.run({ tier: 'probe' }, async () => {
      lateProbeStarted = true;
    });
    await settle();
    expect(lateProbeStarted).toBe(false);

    // ...but creation overflows into the headroom and starts now.
    let creationStarted = false;
    const creation = schedule.run({ tier: 'creation' }, async () => {
      creationStarted = true;
    });
    await settle();
    expect(creationStarted).toBe(true);
    await creation;

    for (const probe of probes) probe.release();
    await Promise.all(probes.map((probe) => probe.done));
    await lateProbe;
    expect(lateProbeStarted).toBe(true);
  });

  it('dispatches queued work by priority, not arrival order', async () => {
    const schedule = new GitSchedule({ capacity: 1, headroom: 0 });
    const running = gated(schedule, 'probe');
    await settle();

    const order: string[] = [];
    const probe = schedule.run({ tier: 'probe' }, async () => {
      order.push('probe');
    });
    const background = schedule.run({ tier: 'background' }, async () => {
      order.push('background');
    });
    const creation = schedule.run({ tier: 'creation' }, async () => {
      order.push('creation');
    });
    await settle();

    running.release();
    await running.done;
    await Promise.all([probe, background, creation]);
    expect(order).toEqual(['creation', 'background', 'probe']);
  });

  it('propagates task failures and frees the slot', async () => {
    const schedule = new GitSchedule({ capacity: 1, headroom: 0 });
    await expect(
      schedule.run({ tier: 'probe' }, async () => {
        throw new Error('boom');
      })
    ).rejects.toThrow('boom');
    // The slot is free again.
    await expect(schedule.run({ tier: 'probe' }, async () => 'ok')).resolves.toBe('ok');
  });

  describe('repository idle gates', () => {
    it('whenIdle waits for queued and in-flight high-tier work on that repository', async () => {
      const schedule = new GitSchedule({ capacity: 1, headroom: 2 });
      const creation = gated(schedule, 'creation', '/repo/a');
      await settle();

      let idle = false;
      const wait = schedule.whenIdle('/repo/a', 5_000).then(() => {
        idle = true;
      });
      await settle();
      expect(idle).toBe(false);

      creation.release();
      await creation.done;
      await wait;
      expect(idle).toBe(true);
    });

    it('whenIdle resolves immediately for a repository with no high-tier work', async () => {
      const schedule = new GitSchedule({ capacity: 2, headroom: 2 });
      const other = gated(schedule, 'creation', '/repo/other');
      await settle();
      await schedule.whenIdle('/repo/quiet', 5_000);
      other.release();
      await other.done;
    });

    it('probes do not hold the idle gate', async () => {
      const schedule = new GitSchedule({ capacity: 2, headroom: 2 });
      const probe = gated(schedule, 'probe', '/repo/a');
      await settle();
      await schedule.whenIdle('/repo/a', 5_000);
      probe.release();
      await probe.done;
    });

    it('withRepoHold keeps the gate closed across a composite operation without a slot', async () => {
      const schedule = new GitSchedule({ capacity: 1, headroom: 0 });
      let releaseHold!: () => void;
      const holding = schedule.withRepoHold('/repo/a', () => {
        return new Promise<void>((resolve) => {
          releaseHold = resolve;
        });
      });
      await settle();

      // The hold consumes no budget slot: a probe still runs...
      await expect(schedule.run({ tier: 'probe' }, async () => 'ran')).resolves.toBe('ran');

      // ...but the repository reads as busy until the hold releases.
      let idle = false;
      const wait = schedule.whenIdle('/repo/a', 5_000).then(() => {
        idle = true;
      });
      await settle();
      expect(idle).toBe(false);
      releaseHold();
      await holding;
      await wait;
      expect(idle).toBe(true);
    });

    it('the deadline bounds starvation: whenIdle resolves even under constant work', async () => {
      const schedule = new GitSchedule({ capacity: 2, headroom: 2 });
      const longRunning = gated(schedule, 'background', '/repo/a');
      await settle();

      const started = Date.now();
      await schedule.whenIdle('/repo/a', 50);
      expect(Date.now() - started).toBeLessThan(5_000);

      longRunning.release();
      await longRunning.done;
    });
  });
});

describe('WorktreeWriteLocks', () => {
  it('a writer excludes probes of that worktree; other worktrees proceed', async () => {
    const { WorktreeWriteLocks } = await import('./git-schedule');
    const locks = new WorktreeWriteLocks();

    let releaseWriter!: () => void;
    const writing = locks.withWriter('/wt/a', () => {
      return new Promise<void>((resolve) => {
        releaseWriter = resolve;
      });
    });
    await settle();

    let probed = false;
    const probe = locks.whenUnlocked('/wt/a').then(() => {
      probed = true;
    });
    await settle();
    expect(probed).toBe(false);

    // A different worktree is not excluded.
    await locks.whenUnlocked('/wt/b');

    releaseWriter();
    await writing;
    await probe;
    expect(probed).toBe(true);
  });

  it('writers of one worktree serialize; failures release the lock', async () => {
    const { WorktreeWriteLocks } = await import('./git-schedule');
    const locks = new WorktreeWriteLocks();
    const order: string[] = [];

    let releaseFirst!: () => void;
    const first = locks.withWriter('/wt/a', () => {
      order.push('first');
      return new Promise<void>((resolve) => {
        releaseFirst = resolve;
      });
    });
    const second = locks.withWriter('/wt/a', async () => {
      order.push('second');
      throw new Error('writer failed');
    });
    await settle();
    expect(order).toEqual(['first']);

    releaseFirst();
    await first;
    await expect(second).rejects.toThrow('writer failed');
    // The failed writer released the lock: probes proceed.
    await locks.whenUnlocked('/wt/a');
  });
});

describe('transient lock retry', () => {
  it('classifies git lock collisions as transient', () => {
    expect(
      isTransientLockError(
        new Error(
          "fatal: Unable to create '/repo/.git/index.lock': File exists.\n" +
            'Another git process seems to be running in this repository'
        )
      )
    ).toBe(true);
    expect(isTransientLockError(new Error('fatal: could not lock ref refs/heads/main'))).toBe(true);
    expect(isTransientLockError(new Error('fatal: not a git repository'))).toBe(false);
  });

  it('retries a transient collision and succeeds; non-transient errors surface at once', async () => {
    let attempts = 0;
    const result = await retryTransientLock(
      async () => {
        attempts += 1;
        if (attempts < 3) {
          throw new Error("Unable to create '/repo/.git/index.lock': File exists.");
        }
        return 'landed';
      },
      { delaysMs: [1, 1, 1] }
    );
    expect(result).toBe('landed');
    expect(attempts).toBe(3);

    let hardAttempts = 0;
    await expect(
      retryTransientLock(
        async () => {
          hardAttempts += 1;
          throw new Error('fatal: pathspec nonsense');
        },
        { delaysMs: [1, 1, 1] }
      )
    ).rejects.toThrow('pathspec');
    expect(hardAttempts).toBe(1);
  });

  it('gives up after the configured retries', async () => {
    let attempts = 0;
    await expect(
      retryTransientLock(
        async () => {
          attempts += 1;
          throw new Error('could not lock ref refs/heads/x');
        },
        { delaysMs: [1, 1] }
      )
    ).rejects.toThrow('could not lock');
    expect(attempts).toBe(3);
  });
});
