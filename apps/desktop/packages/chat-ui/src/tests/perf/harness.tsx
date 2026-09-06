/**
 * perf/harness — shared helpers for the chat-ui performance test suite.
 *
 * Two mount modes:
 *   mountTranscript  — mounts the full <ChatRoot> with virtualizer so total
 *                      load / scroll can be measured end-to-end.
 *   mountRows        — mounts each item via its def.Render directly in a tall
 *                      container, bypassing the virtualizer.  Isolates
 *                      Project-tree render cost from virtualizer overhead.
 *
 * Timing / memory helpers:
 *   now()       — performance.now() alias.
 *   nextPaint() — resolves after two rAF ticks (browser has painted).
 *   heapUsed()  — JS heap snapshot from performance.memory (Chromium only);
 *                 returns undefined in environments that don't support it.
 *   gcHint()    — best-effort GC suggestion via performance.measureUserAgentSpecificMemory
 *                 or window.gc if available; resolves immediately when unsupported.
 *   record()    — structured console.table log for diffing across runs.
 */

import { CachesContext } from '@components/contexts/CachesContext';
import { ThemeContext } from '@components/contexts/ThemeContext';
import { UNIT_REGISTRY, SEGMENTERS } from '@components/engine/unit-registry';
import { createChatCaches } from '@core/caches';
import type { MeasureCtx, RenderCtx } from '@core/define';
import { DEFAULT_THEME } from '@core/theme';
import { For, createSignal } from 'solid-js';
import { render } from 'solid-js/web';
import { createChatContext } from '@/chat-context';
import { ChatRoot } from '@/ChatRoot';
import type { ChatItem } from '@/model';
import type { TranscriptTurn } from '@/model';
import { createChatState } from '@/state/chat-state';

// ── Timing helpers ────────────────────────────────────────────────────────────

/** High-resolution timestamp in milliseconds. */
export const now = (): number => performance.now();

/**
 * Resolves after two requestAnimationFrame ticks, giving the browser time to
 * commit a paint after a DOM-mutating Solid reactive update.
 */
export const nextPaint = (): Promise<void> =>
  new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => resolve());
    });
  });

/**
 * Returns the current JS heap size in bytes (Chromium only).
 * Returns `undefined` in environments that do not expose performance.memory.
 */
export const heapUsed = (): number | undefined =>
  // oxlint-disable-next-line typescript/no-explicit-any -- performance.memory is a non-standard Chromium API
  (performance as any).memory?.usedJSHeapSize as number | undefined;

/**
 * Best-effort GC hint.  Tries `performance.measureUserAgentSpecificMemory`
 * (which forces a GC in supported Chromium builds) and falls back to the
 * `--expose-gc` window.gc shim.  Resolves immediately when unsupported.
 */
export const gcHint = async (): Promise<void> => {
  // oxlint-disable-next-line typescript/no-explicit-any -- non-standard APIs
  const perf = performance as any;
  if (typeof perf.measureUserAgentSpecificMemory === 'function') {
    try {
      await perf.measureUserAgentSpecificMemory();
      return;
    } catch {
      // not in a cross-origin isolated context or not supported — fall through
    }
  }
  // oxlint-disable-next-line typescript/no-explicit-any
  if (typeof (globalThis as any).gc === 'function') {
    // oxlint-disable-next-line typescript/no-explicit-any
    (globalThis as any).gc();
  }
};

// ── Logging ───────────────────────────────────────────────────────────────────

export type PerfRecord = {
  label: string;
  [key: string]: string | number | undefined;
};

/**
 * Log a structured perf record to the console.
 * Outputs as console.table for easy comparison between runs.
 */
export function record(metrics: PerfRecord | PerfRecord[]): void {
  const rows = Array.isArray(metrics) ? metrics : [metrics];
  // eslint-disable-next-line no-console
  console.table(rows);
}

// ── Mount helpers ─────────────────────────────────────────────────────────────

export type Mounted = {
  host: HTMLElement;
  dispose: () => void;
};

/**
 * Mount a full <ChatRoot> in a fixed-size viewport div.
 * Models the same setup as ChatHostExpanded in stories/chat-host.tsx.
 * Returns the host element (for querying) and a dispose function.
 */
export function mountTranscript(
  items: ChatItem[],
  opts: { width?: number; height?: number } = {}
): Mounted {
  const width = opts.width ?? 880;
  const height = opts.height ?? 600;

  const host = document.createElement('div');
  host.style.width = `${width}px`;
  host.style.height = `${height}px`;
  host.style.overflow = 'hidden';
  host.style.position = 'relative';
  document.body.appendChild(host);

  const ctx = createChatContext({ theme: DEFAULT_THEME });
  const state = createChatState(ctx);
  state.transcript.history.seed([
    {
      id: 'perf-turn',
      seq: 0,
      initiator: 'agent',
      items: items.map((item, seq) => ({ ...item, seq })) as TranscriptTurn['items'],
    },
  ]);

  const dispose = render(
    () => <ChatRoot context={ctx} state={state} stickToBottom={false} />,
    host
  );

  return {
    host,
    dispose: () => {
      dispose();
      state.dispose();
      ctx.dispose();
      host.remove();
    },
  };
}

/**
 * Mount every item via its def.Render directly in a tall container.
 * Bypasses the virtualizer so this strictly measures Project render cost.
 *
 * Each item gets a 640px-wide slot at its measured height.
 * Returns the host element and a dispose function.
 */
export function mountRows(items: ChatItem[]): Mounted {
  const width = 640;
  const caches = createChatCaches();
  const segCtx = {
    caches,
    expanded: (_id: string) => false,
    active: false,
    plan: () => null,
    pendingToolCallIds: () => new Set<string>(),
    terminalOutput: () => null,
  };
  const measureCtx: MeasureCtx = {
    theme: DEFAULT_THEME,
    width,
    isCollapsed: (_id: string) => false,
    expanded: (_id: string) => false,
    caches,
  };
  const renderCtx: RenderCtx = {
    viewState: { isCollapsed: (_id: string) => false },
    measureCtx: () => measureCtx,
  };

  const host = document.createElement('div');
  host.style.width = `${width}px`;
  host.style.position = 'relative';
  document.body.appendChild(host);

  // Segment each item into units using SEGMENTERS.
  const allUnits = items.flatMap((item) => {
    const segmenter = SEGMENTERS[item.kind];
    return segmenter ? segmenter.segment(item, segCtx) : [];
  });

  const dispose = render(
    () => (
      <ThemeContext.Provider value={() => DEFAULT_THEME}>
        <CachesContext.Provider value={caches}>
          <div>
            <For each={allUnits}>
              {(u) => {
                const def = UNIT_REGISTRY[u.kind];
                if (!def) return null;
                return <def.Render data={u.data} ctx={renderCtx} vars={def.vars ?? {}} />;
              }}
            </For>
          </div>
        </CachesContext.Provider>
      </ThemeContext.Provider>
    ),
    host
  );

  return {
    host,
    dispose: () => {
      dispose();
      host.remove();
    },
  };
}

/**
 * Build a reactive viewState that can be used with mountTranscript to drive
 * collapse toggles from within tests.
 */
export function makeToggleableViewState() {
  const [flag, setFlag] = createSignal(false);
  return {
    isCollapsed: (id: string): boolean => {
      void id;
      return flag();
    },
    toggleAll: () => setFlag((v) => !v),
    setFlag,
  };
}
