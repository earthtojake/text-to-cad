/**
 * createHeightTween — unit tests.
 *
 * Uses a synchronous, deterministic fake scheduler so no real rAF/timers are
 * needed. Each `sched.flush(timestamp)` runs queued callbacks at that timestamp.
 *
 * Solid's `createEffect` re-runs are scheduled as microtasks, so tests that
 * trigger a signal change must `await Promise.resolve()` before reading the
 * resulting signal values or interacting with the scheduler.
 */

import { createRoot, createSignal } from 'solid-js';
import { describe, expect, it } from 'vitest';
import type { TweenScheduler } from './create-height-tween';
import { createHeightTween } from './create-height-tween';

// ── Synchronous fake scheduler ────────────────────────────────────────────────

type FakeScheduler = TweenScheduler & {
  flush(timestamp: number): void;
  flushAll(startTime?: number, stepMs?: number, limit?: number): number;
  queueLength: () => number;
};

function makeSyncScheduler(nowFn?: () => number): FakeScheduler {
  let nextId = 1;
  const pending = new Map<number, (ts: number) => void>();
  const _now = nowFn ?? (() => 0);

  return {
    request(fn) {
      const id = nextId++;
      pending.set(id, fn);
      return id;
    },
    cancel(id) {
      pending.delete(id);
    },
    now: () => _now(),

    flush(timestamp: number) {
      const entries = [...pending.entries()];
      for (const [id] of entries) pending.delete(id);
      for (const [, fn] of entries) fn(timestamp);
    },
    flushAll(startTime = 0, stepMs = 16, limit = 500) {
      let frames = 0;
      let t = startTime;
      while (pending.size > 0 && frames < limit) {
        this.flush(t);
        t += stepMs;
        frames++;
      }
      return frames;
    },
    queueLength: () => pending.size,
  };
}

// Helper: flush microtasks so Solid effects have a chance to run.
const tick = () => Promise.resolve();

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('createHeightTween — no animation on first mount', () => {
  it('starts at the target value without running any rAF', () => {
    // The initial effect run is synchronous within createRoot.
    const { height, animating, queueLength, cleanup } = createRoot((dispose) => {
      const sched = makeSyncScheduler();
      const { height, animating } = createHeightTween(() => 200, {
        scheduler: sched,
        reducedMotion: () => false,
      });
      return { height, animating, queueLength: sched.queueLength, cleanup: dispose };
    });

    expect(height()).toBe(200);
    expect(animating()).toBe(false);
    expect(queueLength()).toBe(0);
    cleanup();
  });
});

describe('createHeightTween — tween to new target', () => {
  it('interpolates from old to new value and settles exactly at target', async () => {
    let currentTime = 0;
    const sched = makeSyncScheduler(() => currentTime);

    const { height, animating, setTarget, cleanup } = createRoot((dispose) => {
      const [target, setTarget] = createSignal(100);
      const { height, animating } = createHeightTween(target, {
        durationMs: 200,
        scheduler: sched,
        reducedMotion: () => false,
      });
      return { height, animating, setTarget, cleanup: dispose };
    });

    expect(height()).toBe(100);

    // Change target — Solid queues the effect as a microtask.
    setTarget(300);

    // Before awaiting, the effect hasn't re-run yet.
    expect(height()).toBe(100);

    // Flush microtasks: effect runs, starts the rAF loop.
    await tick();

    expect(animating()).toBe(true);
    expect(sched.queueLength()).toBe(1);

    // Halfway through (100ms of 200ms).
    currentTime = 100;
    sched.flush(100);

    const mid = height();
    expect(mid).toBeGreaterThan(100);
    expect(mid).toBeLessThan(300);
    expect(animating()).toBe(true);

    // Run to completion.
    currentTime = 200;
    sched.flush(200);
    sched.flushAll(216, 16); // drain any trailing frames

    expect(height()).toBe(300);
    expect(animating()).toBe(false);
    expect(sched.queueLength()).toBe(0);

    cleanup();
  });

  it('settles at the exact target (no floating-point drift)', async () => {
    const currentTime = 0;
    const sched = makeSyncScheduler(() => currentTime);

    const { height, setTarget, cleanup } = createRoot((dispose) => {
      const [target, setTarget] = createSignal(0);
      const { height } = createHeightTween(target, {
        durationMs: 100,
        scheduler: sched,
        reducedMotion: () => false,
      });
      return { height, setTarget, cleanup: dispose };
    });

    setTarget(99.9);
    await tick(); // let effect run and start rAF loop
    sched.flushAll(0, 16); // drain all frames past the duration
    expect(height()).toBe(99.9);

    cleanup();
  });
});

describe('createHeightTween — retarget mid-flight', () => {
  it('retargets from the current interpolated value when target changes again', async () => {
    let currentTime = 0;
    const sched = makeSyncScheduler(() => currentTime);

    const { height, animating, setTarget, cleanup } = createRoot((dispose) => {
      const [target, setTarget] = createSignal(100);
      const { height, animating } = createHeightTween(target, {
        durationMs: 200,
        scheduler: sched,
        reducedMotion: () => false,
      });
      return { height, animating, setTarget, cleanup: dispose };
    });

    // Start tween 100 → 300.
    setTarget(300);
    await tick(); // effect runs, rAF queued

    currentTime = 100; // halfway
    sched.flush(100);
    const midH = height();
    expect(midH).toBeGreaterThan(100);
    expect(midH).toBeLessThan(300);

    // Retarget mid-flight: 300 → 50.
    setTarget(50);
    await tick(); // effect re-runs, cancels old rAF, queues new one
    expect(animating()).toBe(true);

    // Drain to completion.
    sched.flushAll(116, 16);

    expect(height()).toBe(50);
    expect(animating()).toBe(false);

    cleanup();
  });

  it('starts the new tween from the current height, not the original from-value', async () => {
    let currentTime = 0;
    const sched = makeSyncScheduler(() => currentTime);

    const { height, setTarget, cleanup } = createRoot((dispose) => {
      const [target, setTarget] = createSignal(0);
      const { height } = createHeightTween(target, {
        durationMs: 200,
        scheduler: sched,
        reducedMotion: () => false,
      });
      return { height, setTarget, cleanup: dispose };
    });

    setTarget(200);
    await tick(); // effect runs

    // Run half way.
    currentTime = 100;
    sched.flush(100);
    const snapH = height();
    expect(snapH).toBeGreaterThan(0);

    // Retarget back to 0.
    setTarget(0);
    await tick(); // new effect run starts from snapH

    // Tiny step — height should still be close to snapH, trending toward 0.
    currentTime = 101;
    sched.flush(101);
    const afterRetarget = height();

    expect(afterRetarget).toBeGreaterThan(0);
    expect(afterRetarget).toBeLessThanOrEqual(snapH);

    cleanup();
  });
});

describe('createHeightTween — reduced motion', () => {
  it('snaps instantly to the target without queuing any rAF', async () => {
    const sched = makeSyncScheduler();

    const { height, animating, setTarget, cleanup } = createRoot((dispose) => {
      const [target, setTarget] = createSignal(100);
      const { height, animating } = createHeightTween(target, {
        scheduler: sched,
        reducedMotion: () => true,
      });
      return { height, animating, setTarget, cleanup: dispose };
    });

    setTarget(500);
    await tick(); // effect runs — reduced-motion path: snaps synchronously

    expect(height()).toBe(500);
    expect(animating()).toBe(false);
    expect(sched.queueLength()).toBe(0);

    cleanup();
  });
});

describe('createHeightTween — shouldAnimate gate', () => {
  it('snaps (no rAF) when shouldAnimate returns false', async () => {
    const sched = makeSyncScheduler();

    const { height, animating, setTarget, cleanup } = createRoot((dispose) => {
      const [target, setTarget] = createSignal(100);
      const { height, animating } = createHeightTween(target, {
        scheduler: sched,
        reducedMotion: () => false,
        shouldAnimate: () => false, // layout-settling: always snap
      });
      return { height, animating, setTarget, cleanup: dispose };
    });

    setTarget(400);
    await tick();

    // Snapped instantly — no animation, no queued frames.
    expect(height()).toBe(400);
    expect(animating()).toBe(false);
    expect(sched.queueLength()).toBe(0);

    cleanup();
  });

  it('animates only when shouldAnimate returns true (toggle) and snaps otherwise', async () => {
    let currentTime = 0;
    const sched = makeSyncScheduler(() => currentTime);

    // Emulates UnitRow: a gate that animates only when an external "expanded"
    // signature flips since the last target change.
    let lastSig = false;
    let expandedSig = false;
    const shouldAnimate = () => {
      const changed = expandedSig !== lastSig;
      lastSig = expandedSig;
      return changed;
    };

    const { height, animating, setTarget, cleanup } = createRoot((dispose) => {
      const [target, setTarget] = createSignal(100);
      const { height, animating } = createHeightTween(target, {
        durationMs: 200,
        scheduler: sched,
        reducedMotion: () => false,
        shouldAnimate,
      });
      return { height, animating, setTarget, cleanup: dispose };
    });

    // 1) Layout settle (width/font): target changes but signature unchanged -> snap.
    setTarget(180);
    await tick();
    expect(height()).toBe(180);
    expect(animating()).toBe(false);
    expect(sched.queueLength()).toBe(0);

    // 2) Genuine collapse toggle: flip the signature, then target changes -> animate.
    expandedSig = true;
    setTarget(320);
    await tick();
    expect(animating()).toBe(true);
    expect(sched.queueLength()).toBe(1);

    currentTime = 200;
    sched.flush(200);
    sched.flushAll(216, 16);
    expect(height()).toBe(320);
    expect(animating()).toBe(false);

    // 3) Another layout settle after the toggle: signature unchanged -> snap.
    setTarget(300);
    await tick();
    expect(height()).toBe(300);
    expect(animating()).toBe(false);
    expect(sched.queueLength()).toBe(0);

    cleanup();
  });
});

describe('createHeightTween — no-op when target unchanged', () => {
  it('does not queue a rAF if the target did not change', async () => {
    const sched = makeSyncScheduler();

    const { setTarget, cleanup } = createRoot((dispose) => {
      const [target, setTarget] = createSignal(100);
      createHeightTween(target, { scheduler: sched, reducedMotion: () => false });
      return { setTarget, cleanup: dispose };
    });

    // "Change" to the same value.
    setTarget(100);
    await tick();
    expect(sched.queueLength()).toBe(0);

    cleanup();
  });
});
