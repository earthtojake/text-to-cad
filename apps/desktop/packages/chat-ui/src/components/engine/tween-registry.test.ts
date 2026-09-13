/**
 * createTweenRegistry — unit tests.
 *
 * Tests cover:
 * - First registration: snaps to initial target (no animation on mount).
 * - Target change with shouldAnim=true: kicks off tween; advance() interpolates.
 * - Target change with shouldAnim=false: snaps immediately.
 * - Reduced motion: always snaps.
 * - Retarget mid-flight: starts from current interpolated height.
 * - Settles exactly at target (no float drift).
 * - unregister: removes the entry; subsequent set() creates a fresh entry.
 * - advance() return value: true while active, false when all settled.
 * - height()/animating() are reactive SolidJS signals.
 * - clipHeight(): null at rest, animatedH - gapBefore while animating.
 */

import type { Virtualizer } from '@core/virtualizer';
import { createRoot } from 'solid-js';
import { describe, expect, it, vi } from 'vitest';
import { collapseAnimationDefaults } from './create-height-tween';
import { createTweenRegistry } from './tween-registry';

// ── Fake Virtualizer ──────────────────────────────────────────────────────────

function makeVirt(): Virtualizer {
  const sizes = new Map<number, number>();
  return {
    setSize(index: number, h: number): number {
      const prev = sizes.get(index) ?? 0;
      sizes.set(index, h);
      return h - prev;
    },
    top(_index: number): number {
      return 0;
    },
    total(): number {
      return 0;
    },
  } as unknown as Virtualizer;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('createTweenRegistry — first registration', () => {
  it('snaps to the initial target without animating', () => {
    const virt = makeVirt();
    const onHeightChanged = vi.fn();

    createRoot((dispose) => {
      const reg = createTweenRegistry(virt, onHeightChanged, { reducedMotion: () => false });
      const handle = reg.set('a', () => 0, 100, false);

      expect(handle.height()).toBe(100);
      expect(handle.animating()).toBe(false);
      expect(handle.clipHeight(0)).toBeNull();

      dispose();
    });
  });

  it('calls virt.setSize on first snap registration', () => {
    const virt = makeVirt();
    const onHeightChanged = vi.fn();

    createRoot((dispose) => {
      const reg = createTweenRegistry(virt, onHeightChanged, { reducedMotion: () => false });
      reg.set('a', () => 0, 200, false);
      // Initial registration: delta = 200 - 0 = 200
      expect(onHeightChanged).toHaveBeenCalledWith(0, 200);
      dispose();
    });
  });
});

describe('createTweenRegistry — target change with shouldAnim=true', () => {
  it('sets animating=true and advance() interpolates toward target', () => {
    const virt = makeVirt();
    const onHeightChanged = vi.fn();
    const requestFrame = vi.fn();
    const dur = collapseAnimationDefaults.durationMs;

    createRoot((dispose) => {
      // now: () => 0 so startTime=0; advance timestamps are relative to 0.
      const reg = createTweenRegistry(virt, onHeightChanged, {
        reducedMotion: () => false,
        requestFrame,
        now: () => 0,
      });

      reg.set('a', () => 0, 100, false); // initial snap
      onHeightChanged.mockClear();

      const handle = reg.set('a', () => 0, 300, true); // animate 100→300, startTime=0
      expect(handle.animating()).toBe(true);
      expect(requestFrame).toHaveBeenCalled();

      // At start of tween (t=0), height should still be 100 (not yet advanced).
      expect(handle.height()).toBe(100);

      // Advance to halfway through the duration.
      const moreWork = reg.advance(dur / 2);
      expect(moreWork).toBe(true);

      const mid = handle.height();
      expect(mid).toBeGreaterThan(100);
      expect(mid).toBeLessThan(300);
      expect(handle.animating()).toBe(true);
      expect(handle.clipHeight(0)).not.toBeNull();

      // Advance past the duration end.
      reg.advance(dur * 2);
      expect(handle.height()).toBe(300);
      expect(handle.animating()).toBe(false);
      expect(handle.clipHeight(0)).toBeNull();

      dispose();
    });
  });

  it('advance() returns false when no active entries', () => {
    const virt = makeVirt();
    const reg = createTweenRegistry(virt, () => {}, { reducedMotion: () => false });
    expect(reg.advance(0)).toBe(false);
  });
});

describe('createTweenRegistry — shouldAnim=false snaps', () => {
  it('snaps immediately without animating', () => {
    const virt = makeVirt();
    const onHeightChanged = vi.fn();

    createRoot((dispose) => {
      const reg = createTweenRegistry(virt, onHeightChanged, { reducedMotion: () => false });
      reg.set('a', () => 0, 100, false);
      onHeightChanged.mockClear();

      const handle = reg.set('a', () => 0, 400, false);
      expect(handle.height()).toBe(400);
      expect(handle.animating()).toBe(false);
      expect(onHeightChanged).toHaveBeenCalledWith(0, 300);

      dispose();
    });
  });
});

describe('createTweenRegistry — reduced motion', () => {
  it('always snaps regardless of shouldAnim', () => {
    const virt = makeVirt();

    createRoot((dispose) => {
      const reg = createTweenRegistry(virt, () => {}, { reducedMotion: () => true });
      reg.set('a', () => 0, 100, false);

      const handle = reg.set('a', () => 0, 500, true); // reduced motion → snap
      expect(handle.height()).toBe(500);
      expect(handle.animating()).toBe(false);

      dispose();
    });
  });
});

describe('createTweenRegistry — retarget mid-flight', () => {
  it('starts the new tween from the current interpolated height', () => {
    const virt = makeVirt();
    const dur = collapseAnimationDefaults.durationMs;

    createRoot((dispose) => {
      const reg = createTweenRegistry(virt, () => {}, {
        reducedMotion: () => false,
        now: () => 0,
      });
      reg.set('a', () => 0, 0, false); // initial snap; startTime=0

      // Arm first tween: 0→200, startTime = nowVal = 0.
      reg.set('a', () => 0, 200, true);

      // Advance halfway: elapsed = dur/2.
      reg.advance(dur / 2);
      const midH = reg.set('a', () => 0, 200, true).height(); // peek current height
      expect(midH).toBeGreaterThan(0);
      expect(midH).toBeLessThan(200);

      // Retarget to 50. nowVal still 0, so startTime=0 for the new tween.
      // The new tween starts from midH toward 50.
      const h2 = reg.set('a', () => 0, 50, true);
      expect(h2.height()).toBe(midH);
      expect(h2.animating()).toBe(true);

      // Advance a tiny bit more (from t=0 of new tween).
      reg.advance(dur * 0.01);
      const afterStep = h2.height();
      // Should be moving from midH toward 50 (decreasing).
      expect(afterStep).toBeLessThan(midH);

      dispose();
    });
  });

  it('settles exactly at the target (no float drift)', () => {
    const virt = makeVirt();
    const dur = collapseAnimationDefaults.durationMs;

    createRoot((dispose) => {
      const reg = createTweenRegistry(virt, () => {}, {
        reducedMotion: () => false,
        now: () => 0,
      });
      reg.set('a', () => 0, 0, false);
      const handle = reg.set('a', () => 0, 99.9, true); // startTime=0

      // Advance well past the duration.
      reg.advance(dur * 10);

      expect(handle.height()).toBe(99.9);
      expect(handle.animating()).toBe(false);

      dispose();
    });
  });
});

describe('createTweenRegistry — unregister', () => {
  it('removes the entry; subsequent set() creates a fresh entry', () => {
    const virt = makeVirt();

    createRoot((dispose) => {
      const reg = createTweenRegistry(virt, () => {}, { reducedMotion: () => false });
      reg.set('a', () => 0, 100, false);

      reg.unregister('a');

      // New registration starts fresh at the new target.
      const handle = reg.set('a', () => 0, 200, false);
      expect(handle.height()).toBe(200);
      expect(handle.animating()).toBe(false);

      dispose();
    });
  });
});

describe('createTweenRegistry — clipHeight', () => {
  it('returns null at rest and animatedH - gapBefore while animating', () => {
    const virt = makeVirt();
    const dur = collapseAnimationDefaults.durationMs;

    createRoot((dispose) => {
      const reg = createTweenRegistry(virt, () => {}, {
        reducedMotion: () => false,
        now: () => 0,
      });
      reg.set('a', () => 0, 100, false);

      const handle = reg.set('a', () => 0, 200, true); // startTime=0
      reg.advance(dur / 4);

      const h = handle.height();
      const gapBefore = 16;
      const clip = handle.clipHeight(gapBefore);
      expect(clip).not.toBeNull();
      expect(clip).toBeCloseTo(h - gapBefore, 5);

      // At rest, clipHeight should be null.
      reg.advance(dur * 10);
      expect(handle.clipHeight(gapBefore)).toBeNull();

      dispose();
    });
  });
});

describe('createTweenRegistry — multiple simultaneous entries', () => {
  it('advances all active entries per frame; returns false when all settle', () => {
    const virt = makeVirt();
    const dur = collapseAnimationDefaults.durationMs;

    createRoot((dispose) => {
      const reg = createTweenRegistry(virt, () => {}, {
        reducedMotion: () => false,
        now: () => 0,
      });

      // Snap both to starting positions.
      reg.set('a', () => 0, 100, false);
      reg.set('b', () => 1, 50, false);

      // Arm tweens for both; startTime = 0 for both.
      const ha = reg.set('a', () => 0, 300, true);
      const hb = reg.set('b', () => 1, 200, true);

      expect(ha.animating()).toBe(true);
      expect(hb.animating()).toBe(true);

      // Both active at halfway: advance returns true.
      expect(reg.advance(dur / 2)).toBe(true);

      // Both should be mid-tween.
      expect(ha.height()).toBeGreaterThan(100);
      expect(hb.height()).toBeGreaterThan(50);

      // Run to end.
      reg.advance(dur * 10);

      expect(ha.height()).toBe(300);
      expect(hb.height()).toBe(200);
      // Both settled: advance returns false.
      expect(reg.advance(dur * 20)).toBe(false);

      dispose();
    });
  });
});
