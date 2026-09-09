/**
 * Collapse animation perf bench.
 *
 * Measures rAF frame times during a programmatic expand/collapse cycle on a
 * large list to verify that the tween cost is O(log n) rather than
 * O(scroll-region-size). The story mounts a 2k or 10k transcript, pre-expands
 * a thinking block near the top, then collapses and re-expands it once the
 * virtualizer has settled, recording frame times throughout.
 *
 * Open the story and inspect the browser console for a summary table. Target:
 *   p95 frame time at 10k ≈ p95 frame time at 2k  (within ~1 frame / ~16ms).
 */

import { DEFAULT_THEME } from '@core/theme';
import { createSignal, onCleanup, onMount } from 'solid-js';
import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { createChatContext } from '@/chat-context';
import { createChatView } from '@/chat-view';
import type { ChatView } from '@/chat-view';
import { generateMockTranscript } from '@/mock-transcript';
import type { TranscriptTurn } from '@/model';
import { createChatState } from '@/state/chat-state';
import type { FrameStats } from '@/stories/_harness/perf-instrument';

const meta: Meta = {
  title: 'Perf/CollapseAnimation',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

// ── Types ─────────────────────────────────────────────────────────────────────

type AnimBenchResult = {
  collapseFrames: FrameStats;
  expandFrames: FrameStats;
};

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Record rAF frame deltas until the animation settles (no new frame for
 * `settleMs` after the last one), or until `maxMs` elapses.
 */
function measureFrames(settleMs = 350, maxMs = 2000): Promise<FrameStats> {
  return new Promise((resolve) => {
    const deltas: number[] = [];
    let last = performance.now();
    let raf = 0;
    let settleTimer: ReturnType<typeof setTimeout> | null = null;
    const deadline = performance.now() + maxMs;

    function done() {
      cancelAnimationFrame(raf);
      if (settleTimer !== null) clearTimeout(settleTimer);
      resolve(stats(deltas));
    }

    function tick(now: number) {
      deltas.push(now - last);
      last = now;
      if (settleTimer !== null) clearTimeout(settleTimer);
      if (now > deadline) {
        done();
        return;
      }
      settleTimer = setTimeout(done, settleMs);
      raf = requestAnimationFrame(tick);
    }

    raf = requestAnimationFrame(tick);
  });
}

function stats(deltas: number[]): FrameStats {
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

// ── Bench component ───────────────────────────────────────────────────────────

function CollapseAnimBench(props: { count: number; label: string }) {
  const [result, setResult] = createSignal<string>('Mounting…');
  let containerEl: HTMLDivElement | undefined;
  let viewRef: ChatView | null = null;

  const TOGGLE_ID = 'bench-think';
  const baseTurns = generateMockTranscript(props.count);
  const turns: TranscriptTurn[] = [
    {
      id: 'bench-thinking-turn',
      seq: 0,
      initiator: 'agent',
      items: [
        {
          kind: 'thinking',
          id: TOGGLE_ID,
          seq: 0,
          segmentId: TOGGLE_ID,
          text: 'This is the thinking block that will be toggled during the benchmark. It contains enough text to produce a meaningful height change that exercises the full tween path. The expand and collapse directions should both be measured.',
          status: 'done',
          durationMs: 2000,
          startedAt: Date.now() - 2000,
        },
      ],
      outcome: { kind: 'done' },
    },
    ...baseTurns.map((turn, index) => ({ ...turn, seq: index + 1 })),
  ];

  onMount(() => {
    if (!containerEl) return;

    const ctx = createChatContext({ theme: DEFAULT_THEME });
    const state = createChatState(ctx);

    state.transcript.history.seed(turns);

    const view = createChatView({
      context: ctx,
      state,
      parent: containerEl,
      onViewMounted: (v) => {
        viewRef = v;
      },
    });

    onCleanup(() => {
      view.dispose();
      state.dispose();
      ctx.dispose();
    });

    // Give the virtualizer two frames to measure and lay out rows.
    requestAnimationFrame(() => {
      requestAnimationFrame(async () => {
        const v = viewRef;
        if (!v) return;

        setResult('Collapsing…');
        const collapseP = measureFrames();
        v.toggleCollapsed(TOGGLE_ID);
        const collapseFrames = await collapseP;

        await new Promise<void>((r) => setTimeout(r, 50));

        setResult('Expanding…');
        const expandP = measureFrames();
        v.toggleCollapsed(TOGGLE_ID);
        const expandFrames = await expandP;

        const bench: AnimBenchResult = { collapseFrames, expandFrames };

        const lines = [
          `=== ${props.label} — collapse/expand animation bench ===`,
          `Collapse: ${collapseFrames.count} frames  avg:${collapseFrames.avgMs}ms  p50:${collapseFrames.p50Ms}ms  p95:${collapseFrames.p95Ms}ms  max:${collapseFrames.maxMs}ms`,
          `Expand:   ${expandFrames.count} frames  avg:${expandFrames.avgMs}ms  p50:${expandFrames.p50Ms}ms  p95:${expandFrames.p95Ms}ms  max:${expandFrames.maxMs}ms`,
        ].join('\n');
        console.log(lines);
        console.table({
          collapse_avg: bench.collapseFrames.avgMs,
          collapse_p50: bench.collapseFrames.p50Ms,
          collapse_p95: bench.collapseFrames.p95Ms,
          collapse_max: bench.collapseFrames.maxMs,
          expand_avg: bench.expandFrames.avgMs,
          expand_p50: bench.expandFrames.p50Ms,
          expand_p95: bench.expandFrames.p95Ms,
          expand_max: bench.expandFrames.maxMs,
        });
        setResult(lines);
      });
    });
  });

  return (
    <div>
      <div
        ref={(el) => {
          containerEl = el;
        }}
        style={{
          width: '640px',
          height: '700px',
          border: '1px solid #e2e8f0',
          'border-radius': '8px',
          overflow: 'hidden',
        }}
      />
      <pre
        style={{
          'margin-top': '12px',
          padding: '12px',
          background: '#f1f5f9',
          'border-radius': '6px',
          'font-size': '12px',
          'white-space': 'pre-wrap',
        }}
      >
        {result()}
      </pre>
    </div>
  );
}

// ── Stories ───────────────────────────────────────────────────────────────────

export const TwoK: Story = {
  name: '2k rows — collapse/expand bench',
  render: () => <CollapseAnimBench count={2000} label="2k rows" />,
};

export const TenK: Story = {
  name: '10k rows — collapse/expand bench',
  render: () => <CollapseAnimBench count={10000} label="10k rows" />,
};
