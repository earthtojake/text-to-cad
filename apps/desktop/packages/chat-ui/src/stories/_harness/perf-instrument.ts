/**
 * Perf instrumentation utilities for chat-ui scroll performance profiling.
 *
 * Three complementary counters:
 *   1. rAF frame-time distribution — avg/p50/p95/max ms during a scripted scroll sweep.
 *   2. MutationObserver DOM node-churn count — proves slot-pool removes create/destroy.
 *   3. Row component-creation counter — a module-level increment for Row() calls.
 *
 * Usage: see perf.stories.tsx.
 */

// ── Row creation counter ──────────────────────────────────────────────────────
// Row() increments this on every component instantiation.
let rowCreations = 0;
export function bumpRowCreations(): void {
  rowCreations++;
}
export function getRowCreations(): number {
  return rowCreations;
}
export function resetRowCreations(): void {
  rowCreations = 0;
}

// ── Frame-time recorder ───────────────────────────────────────────────────────

export type FrameStats = {
  count: number;
  avgMs: number;
  p50Ms: number;
  p95Ms: number;
  maxMs: number;
};

function frameStats(deltas: number[]): FrameStats {
  if (deltas.length === 0) return { count: 0, avgMs: 0, p50Ms: 0, p95Ms: 0, maxMs: 0 };
  const sorted = [...deltas].sort((a, b) => a - b);
  const avg = sorted.reduce((s, x) => s + x, 0) / sorted.length;
  const p = (pct: number) => sorted[Math.floor(sorted.length * pct)] ?? sorted[sorted.length - 1];
  return {
    count: sorted.length,
    avgMs: +avg.toFixed(2),
    p50Ms: +p(0.5).toFixed(2),
    p95Ms: +p(0.95).toFixed(2),
    maxMs: +sorted[sorted.length - 1].toFixed(2),
  };
}

/**
 * Run a constant-velocity scroll sweep from top to bottom of `scrollEl` over
 * `durationMs`, recording rAF inter-frame deltas. Returns frame stats.
 */
export function sweepScroll(
  scrollEl: HTMLElement,
  durationMs = 2000
): Promise<{ frames: FrameStats; churn: ChurnStats }> {
  return new Promise((resolve) => {
    const total = scrollEl.scrollHeight - scrollEl.clientHeight;
    if (total <= 0) {
      resolve({ frames: frameStats([]), churn: churnStats([]) });
      return;
    }

    const churnSamples: number[] = [];
    const obs = new MutationObserver((mutations) => {
      let n = 0;
      for (const m of mutations) n += m.addedNodes.length + m.removedNodes.length;
      if (n > 0) churnSamples.push(n);
    });
    const canvas = scrollEl.querySelector('[data-chat-canvas]') ?? scrollEl;
    obs.observe(canvas, { childList: true, subtree: true });

    const frameTimes: number[] = [];
    let lastRaf = performance.now();
    let startTime = performance.now();

    function tick(now: number) {
      frameTimes.push(now - lastRaf);
      lastRaf = now;

      const elapsed = now - startTime;
      const frac = Math.min(elapsed / durationMs, 1);
      scrollEl.scrollTop = Math.round(frac * total);
      scrollEl.dispatchEvent(new Event('scroll'));

      if (frac < 1) {
        requestAnimationFrame(tick);
      } else {
        obs.disconnect();
        resolve({ frames: frameStats(frameTimes), churn: churnStats(churnSamples) });
      }
    }

    scrollEl.scrollTop = 0;
    startTime = performance.now();
    lastRaf = startTime;
    requestAnimationFrame(tick);
  });
}

// ── DOM churn stats ───────────────────────────────────────────────────────────

export type ChurnStats = {
  totalMutations: number;
  totalNodes: number;
  avgNodesPerMutation: number;
};

function churnStats(samples: number[]): ChurnStats {
  if (samples.length === 0) return { totalMutations: 0, totalNodes: 0, avgNodesPerMutation: 0 };
  const total = samples.reduce((s, x) => s + x, 0);
  return {
    totalMutations: samples.length,
    totalNodes: total,
    avgNodesPerMutation: +(total / samples.length).toFixed(1),
  };
}

// ── Combined run ──────────────────────────────────────────────────────────────

export type PerfResult = {
  label: string;
  frames: FrameStats;
  churn: ChurnStats;
  rowCreationsDuringRun: number;
};

export async function runPerfSweep(
  label: string,
  scrollEl: HTMLElement,
  durationMs = 2000
): Promise<PerfResult> {
  const before = getRowCreations();
  const { frames, churn } = await sweepScroll(scrollEl, durationMs);
  const after = getRowCreations();
  return { label, frames, churn, rowCreationsDuringRun: after - before };
}
