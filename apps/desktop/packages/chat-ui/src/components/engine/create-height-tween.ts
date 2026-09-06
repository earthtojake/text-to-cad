/**
 * createHeightTween — reactive rAF-based height interpolator for collapse/expand.
 *
 * Tracks a `target` accessor and smoothly tweens toward it whenever it changes.
 * Returns `{ height, animating }` — feed `height()` into `virt.setSize` so
 * rows below reposition in lockstep with the animated row.
 *
 * Design:
 * - First mount: height starts at target (no animation — avoids flash on load).
 * - On target change: captures `from = height()` (untracked) and eases to the
 *   new target over `durationMs` with easeOutCubic.
 * - `shouldAnimate` gate: consulted on each target change; when false the new
 *   target is applied instantly (snap). Use it to animate only genuine
 *   transitions while snapping layout settling (width/font/streaming).
 * - Retarget mid-flight: createEffect re-runs whenever target changes; onCleanup
 *   cancels the in-progress rAF loop so the next tween starts from the current
 *   intermediate value (handles rapid re-toggles cleanly).
 * - prefers-reduced-motion: snaps instantly, no rAF overhead.
 * - The effect depends ONLY on `target` (height is read untracked) so the
 *   per-frame setHeight does not re-enter and restart the tween.
 * - `scheduler` is injectable for deterministic Node tests without real timers.
 */

import { createEffect, createSignal, onCleanup, untrack } from 'solid-js';
import type { Accessor } from 'solid-js';

// ── Easing ────────────────────────────────────────────────────────────────────

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3;
}

// ── Scheduler interface ───────────────────────────────────────────────────────

export type TweenScheduler = {
  request(fn: (timestamp: number) => void): number;
  cancel(id: number): void;
  now(): number;
};

const defaultScheduler: TweenScheduler = {
  request: (fn) => requestAnimationFrame(fn),
  cancel: (id) => cancelAnimationFrame(id),
  now: () => performance.now(),
};

// ── Reduced-motion detection ──────────────────────────────────────────────────

function defaultReducedMotion(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// ── Global default (overridable for stories / tests) ─────────────────────────

/**
 * Module-level default duration used when `opts.durationMs` is not supplied.
 * Stories can write to this to tune the animation without prop-drilling.
 *
 * Usage in a story decorator or story render fn:
 *   import { collapseAnimationDefaults } from '…/create-height-tween';
 *   collapseAnimationDefaults.durationMs = 600;
 */
export const collapseAnimationDefaults = {
  durationMs: 200,
};

// ── Options ───────────────────────────────────────────────────────────────────

export type HeightTweenOptions = {
  /** Animation duration in ms (default: collapseAnimationDefaults.durationMs = 200). */
  durationMs?: number;
  /** Injectable scheduler for tests — defaults to rAF/performance.now(). */
  scheduler?: TweenScheduler;
  /** Override reduced-motion check — defaults to matchMedia. */
  reducedMotion?: () => boolean;
  /**
   * Consulted (untracked) at the moment a target change is detected. When it
   * returns false, the new target is applied instantly (snap) instead of
   * animating. Use this to animate only genuine, user-driven transitions while
   * snapping for layout settling (width measurement, font load, streaming
   * growth, resizes). Defaults to always-animate.
   */
  shouldAnimate?: () => boolean;
};

// ── createHeightTween ─────────────────────────────────────────────────────────

export type HeightTweenResult = {
  /** Animated height — use instead of `target()` for virt.setSize. */
  height: Accessor<number>;
  /** True while a tween is in progress — use to gate clip/debug-overlay logic. */
  animating: Accessor<boolean>;
};

export function createHeightTween(
  target: Accessor<number>,
  opts: HeightTweenOptions = {}
): HeightTweenResult {
  const {
    // Fall through to the module-level default so stories can tune it.
    durationMs = collapseAnimationDefaults.durationMs,
    scheduler = defaultScheduler,
    reducedMotion = defaultReducedMotion,
    shouldAnimate = () => true,
  } = opts;

  // Initialize at target so the first mount has no animation.
  const [height, setHeight] = createSignal(target());
  const [animating, setAnimating] = createSignal(false);

  createEffect(() => {
    const to = target();
    // Read the current height untracked so this effect depends ONLY on `target`.
    // (If it tracked `height`, every per-frame setHeight would re-run the effect,
    // cancel the rAF, and restart the tween — it would never settle.)
    const from = untrack(height);

    // Evaluate the gate up front (unless reduced motion forces a snap) so a
    // caller using it for change-detection stays in sync on every target change.
    const animate = !reducedMotion() && untrack(shouldAnimate);

    // Snap immediately when: no real change, reduced motion, or the gate says
    // this target change is not an animatable transition (e.g. layout settling
    // such as width measurement, font load, or streaming growth).
    if (from === to || !animate) {
      setHeight(to);
      setAnimating(false);
      return;
    }

    setAnimating(true);
    const startTime = scheduler.now();

    let rafId: number;

    function tick(now: number) {
      const elapsed = now - startTime;
      const t = Math.min(1, elapsed / durationMs);
      const eased = easeOutCubic(t);
      const next = from + (to - from) * eased;

      setHeight(next);

      if (t < 1) {
        rafId = scheduler.request(tick);
      } else {
        // Ensure we land exactly on target to avoid floating-point drift.
        setHeight(to);
        setAnimating(false);
      }
    }

    rafId = scheduler.request(tick);

    // Cancelled when target changes mid-flight (onCleanup runs before the next
    // effect execution). The next effect starts from `height()` which is the
    // current interpolated value, so retargeting is smooth.
    onCleanup(() => {
      scheduler.cancel(rafId);
      // Don't clear animating here — the next effect will set it appropriately.
    });
  });

  return { height, animating };
}
