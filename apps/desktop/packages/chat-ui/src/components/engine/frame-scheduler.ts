/**
 * createFrameScheduler — a demand-driven, phased rAF loop.
 *
 * Enforces a strict read → animate → write phase ordering per frame so DOM
 * geometry reads (scrollTop/clientHeight) are always batched before any writes.
 * The loop re-schedules only when a phase signals more work is pending, so it
 * sleeps completely when the UI is idle (no battery cost from a perpetual rAF).
 *
 * Hardened invariants (aligned with CodeMirror's measure cycle):
 *
 * 1. Liveness-through-failure: phases run inside try/catch; the re-arm
 *    decision always executes in `finally` so a throwing phase cannot
 *    permanently stall the loop.
 *
 * 2. Bounded converge: if write returns true more than MAX_CONVERGE consecutive
 *    frames the loop stops re-arming to prevent a spin loop. A warning is
 *    logged in development.
 *
 * 3. Force-reconcile: `forceReconcile()` marks work pending and arms the loop.
 *    Call on view (re)attach or when the viewport becomes visible after being
 *    hidden (inert / visibility:hidden) to self-heal any missed wakes.
 *
 * Phases:
 *   read     — read DOM geometry once per frame into signals (shadow).
 *   animate  — advance all active tweens; return true while any remain active.
 *   write    — flush coalesced height total and apply at most one scroll write;
 *              return true if more write work was queued this tick.
 *
 * Usage:
 *   const scheduler = createFrameScheduler({ read, animate, write });
 *   scheduler.request();        // arm from any event handler or tween start
 *   scheduler.forceReconcile(); // re-arm + mark dirty on reattach/visibility
 *   scheduler.dispose();        // cancel in onCleanup
 */

const MAX_CONVERGE = 6;

export type FrameSchedulerPhases = {
  read: () => void;
  animate: () => boolean;
  write: () => boolean;
};

export type FrameScheduler = {
  /** Arm the loop for the next frame (idempotent if already requested). */
  request: () => void;
  /**
   * Force-dirty + arm. Call on view (re)attach or visibility regain to
   * self-heal any stale DOM state from missed wakes while hidden/inert.
   * Invokes the provided `onForce` callback (if any) before arming.
   */
  forceReconcile: (onForce?: () => void) => void;
  /** Cancel any pending frame. Call in onCleanup. */
  dispose: () => void;
};

export function createFrameScheduler(phases: FrameSchedulerPhases): FrameScheduler {
  let rafId: number | null = null;
  let consecutiveWrites = 0;

  const tick = () => {
    rafId = null;
    let moreAnimate = false;
    let moreWrite = false;
    try {
      phases.read();
      moreAnimate = phases.animate();
      moreWrite = phases.write();
    } catch (err) {
      if (import.meta.env.DEV) {
        console.error('[chat-ui] frame scheduler phase error', err);
      }
    } finally {
      let halted = false;
      if (moreWrite) {
        consecutiveWrites++;
        if (consecutiveWrites > MAX_CONVERGE) {
          if (import.meta.env.DEV) {
            console.warn(
              `[chat-ui] frame scheduler write loop restarted more than ${MAX_CONVERGE} times — halting converge.`
            );
          }
          consecutiveWrites = 0;
          halted = true;
        }
      } else {
        consecutiveWrites = 0;
      }
      if (!halted && (moreAnimate || moreWrite)) request();
    }
  };

  const request = () => {
    if (rafId === null) rafId = requestAnimationFrame(tick);
  };

  const forceReconcile = (onForce?: () => void) => {
    onForce?.();
    request();
  };

  const dispose = () => {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  };

  return { request, forceReconcile, dispose };
}
