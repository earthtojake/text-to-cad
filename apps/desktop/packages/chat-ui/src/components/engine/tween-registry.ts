/**
 * createTweenRegistry — central height-tween store advanced by the frame scheduler.
 *
 * Replaces per-row createHeightTween rAF loops with a single registry that is
 * advanced once per frame in the scheduler's animate phase. All tween logic
 * (easing, shouldAnimate gate, reduced-motion snap, retarget mid-flight) is
 * preserved from create-height-tween.ts.
 *
 * Key design points:
 * - Entries are keyed by stable **unitId** (not index) so multiple render
 *   units from one item remain independent and survive re-flatten.
 * - Each entry owns a pair of SolidJS signals (height, animating) created in
 *   an isolated owner root that is disposed on unregister.
 * - UnitRow registers its target via `registry.set(itemId, getIndex, target,
 *   shouldAnimate)` from a reactive effect; the registry detects target changes
 *   and decides snap-vs-animate the same way createHeightTween did.
 * - `advance(now)` is called by the frame scheduler; it interpolates all active
 *   entries, calls virt.setSize + onHeightChanged, and returns true while any
 *   entry is still animating so the scheduler stays awake.
 * - `height(itemId)` / `animating(itemId)` / `clipHeight(itemId, logicalH)` are
 *   reactive read accessors for UnitRow to build its RenderCtx.
 */

import type { Virtualizer } from '@core/virtualizer';
import { createRoot, createSignal } from 'solid-js';
import type { Accessor, Setter } from 'solid-js';
import { collapseAnimationDefaults } from './create-height-tween';

// ── Easing ────────────────────────────────────────────────────────────────────

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3;
}

// ── Reduced-motion detection ──────────────────────────────────────────────────

function defaultReducedMotion(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// ── Types ─────────────────────────────────────────────────────────────────────

type TweenEntry = {
  /** Current tween start value (height at the moment the target changed). */
  from: number;
  /** Target height we are interpolating toward. */
  to: number;
  /** Timestamp (ms) when this tween started. */
  startTime: number;
  /** Whether a tween is currently in-flight for this entry. */
  active: boolean;
  /** Returns the current row index — may change across re-flattens. */
  getIndex: () => number;
  /** Reactive signal getter — read by UnitRow to drive layout. */
  height: Accessor<number>;
  setHeight: Setter<number>;
  /** Reactive signal getter — read by UnitRow to drive clip/display state. */
  animating: Accessor<boolean>;
  setAnimating: Setter<boolean>;
  /** Disposes the isolated SolidJS owner that owns the signals. */
  disposeOwner: () => void;
};

export type TweenHandle = {
  /** Animated height reactive accessor — use for virt.setSize. */
  height: Accessor<number>;
  /** True while a tween is in progress. */
  animating: Accessor<boolean>;
  /**
   * Animated content-clip height. Non-null only while animating; use to clip
   * the content container and track card borders through the tween.
   * `gapBefore` is subtracted to convert row-reserved height to content height.
   */
  clipHeight: (gapBefore: number) => number | null;
};

export type TweenRegistry = {
  /**
   * Called by UnitRow (from a reactive effect) whenever the row's logical
   * reserved height or expand state changes. The registry detects a target
   * change and decides whether to animate or snap.
   *
   * @param unitId      Stable render-unit identifier (not the row index).
   * @param getIndex    Reactive function returning the current row index.
   * @param target      New logical reserved height.
   * @param shouldAnim  True iff this target change should be animated (vs snap).
   * @returns           Reactive handle for height/animating/clipHeight.
   */
  set(unitId: string, getIndex: () => number, target: number, shouldAnim: boolean): TweenHandle;
  /**
   * Called by UnitRow's onCleanup to remove the entry when the row unmounts.
   */
  unregister(unitId: string): void;
  /**
   * Advance all active tweens by one frame. Call from the scheduler's animate
   * phase. Returns true while any entry is still mid-tween (keeps scheduler awake).
   */
  advance(now: number): boolean;
};

// ── createTweenRegistry ───────────────────────────────────────────────────────

export type TweenRegistryOptions = {
  durationMs?: number;
  reducedMotion?: () => boolean;
  /**
   * Called when a new tween is armed so the frame scheduler wakes up.
   * In ChatRoot this calls `schedulerRef.request()`. Optional; falls back to a
   * standalone rAF (useful for tests that don't use the frame scheduler).
   */
  requestFrame?: () => void;
  /**
   * Clock function for recording tween start times. Defaults to
   * `performance.now()`. Override in tests for deterministic timing.
   */
  now?: () => number;
};

export function createTweenRegistry(
  virt: Virtualizer,
  onHeightChanged: (index: number, delta: number) => void,
  opts: TweenRegistryOptions = {}
): TweenRegistry {
  const {
    reducedMotion = defaultReducedMotion,
    requestFrame,
    now: nowFn = () => performance.now(),
  } = opts;

  const armScheduler =
    requestFrame ??
    (() => {
      // Fallback for environments without a frame scheduler (tests, stories).
      // A single rAF is enough; the registry will re-arm via advance() returning true.
      if (typeof requestAnimationFrame !== 'undefined') requestAnimationFrame(() => {});
    });

  const entries = new Map<string, TweenEntry>();

  // Cache reduced-motion per-advance to avoid repeated matchMedia queries.
  let reducedMotionCache = reducedMotion();

  const set = (
    unitId: string,
    getIndex: () => number,
    target: number,
    shouldAnim: boolean
  ): TweenHandle => {
    const existing = entries.get(unitId);

    if (!existing) {
      // First registration: create the isolated owner + signals.
      let height!: Accessor<number>;
      let setHeight!: Setter<number>;
      let animating!: Accessor<boolean>;
      let setAnimating!: Setter<boolean>;
      let disposeOwner!: () => void;

      createRoot((dispose) => {
        disposeOwner = dispose;
        [height, setHeight] = createSignal(target);
        [animating, setAnimating] = createSignal(false);
      });

      const entry: TweenEntry = {
        from: target,
        to: target,
        startTime: 0,
        active: false,
        getIndex,
        height,
        setHeight,
        animating,
        setAnimating,
        disposeOwner,
      };
      entries.set(unitId, entry);

      // Register the initial size in the virtualizer so its internal state
      // matches the row's known height from the start.
      const initialDelta = virt.setSize(getIndex(), target);
      if (initialDelta !== 0) onHeightChanged(getIndex(), initialDelta);

      return makeHandle(entry);
    }

    // Existing entry: update getIndex in case the row shifted due to prepend/re-flatten.
    existing.getIndex = getIndex;

    if (target === existing.to) {
      // Target unchanged — no work needed.
      return makeHandle(existing);
    }

    // Target changed. Decide snap vs. animate.
    const currentH = existing.height();
    const noMotion = reducedMotionCache || !shouldAnim;

    if (noMotion || currentH === target) {
      // Snap immediately.
      existing.from = target;
      existing.to = target;
      existing.active = false;
      existing.setHeight(target);
      existing.setAnimating(false);
      const delta = virt.setSize(getIndex(), target);
      if (delta !== 0) onHeightChanged(getIndex(), delta);
    } else {
      // Kick off a tween from the current animated height.
      // Capture startTime immediately so elapsed is correct on the first advance.
      existing.from = currentH;
      existing.to = target;
      existing.startTime = nowFn();
      existing.active = true;
      existing.setAnimating(true);
      // Arm the frame scheduler so advance() runs next frame.
      armScheduler();
    }

    return makeHandle(existing);
  };

  const unregister = (unitId: string) => {
    const entry = entries.get(unitId);
    if (entry) {
      entry.disposeOwner();
      entries.delete(unitId);
    }
  };

  const advance = (now: number): boolean => {
    // Refresh reduced-motion once per frame.
    reducedMotionCache = reducedMotion();

    const durationMs = collapseAnimationDefaults.durationMs;
    let anyActive = false;

    for (const [, entry] of entries) {
      if (!entry.active) continue;

      const elapsed = now - entry.startTime;
      const t = Math.min(1, elapsed / durationMs);
      const eased = easeOutCubic(t);
      const h = entry.from + (entry.to - entry.from) * eased;

      const idx = entry.getIndex();
      const delta = virt.setSize(idx, h);
      if (delta !== 0) onHeightChanged(idx, delta);

      entry.setHeight(h);

      if (t >= 1) {
        // Tween finished — land exactly on the target to eliminate float drift.
        entry.setHeight(entry.to);
        entry.active = false;
        entry.setAnimating(false);
      } else {
        anyActive = true;
      }
    }

    return anyActive;
  };

  return { set, unregister, advance };
}

// ── makeHandle — reactive accessor bundle for UnitRow ─────────────────────────

function makeHandle(entry: TweenEntry): TweenHandle {
  return {
    height: entry.height,
    animating: entry.animating,
    clipHeight: (gapBefore: number) => (entry.animating() ? entry.height() - gapBefore : null),
  };
}
