/**
 * Repro: blank transcript after fast tab switching (history present but no rows).
 *
 * Targets the *current* failure mode (distinct from the old memo-based one the
 * fast-switch story guards): after a rapid setModel swap the viewport renders
 * zero rows even though the active ChatState has committed history. Sending a
 * message (a named scroll event) restores it.
 *
 * Suspected triggers (toggle via controls to find which reproduces):
 *   - asyncSeedMs > 0   : history is seeded AFTER the switch (mimics IPC load).
 *   - keepStreaming     : an active turn is open when you switch away/back.
 *   - intent 'anchor'   : long tab parked near the bottom → scrollTop may end up
 *                         out of range for a shorter tab (computeVisible start
 *                         > visEnd → empty window).
 *   - thrashMs small    : switch faster than one frame (~16ms).
 *
 * The status line shows "⚠ BLANK ..." with scroll geometry when the active tab
 * has data but renders 0 rows. That is the bug.
 */

import { DEFAULT_THEME } from '@core/theme';
import { For, Show, createEffect, createSignal, onCleanup, onMount } from 'solid-js';
import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { createChatContext } from '@/chat-context';
import type { ChatView } from '@/chat-view';
import { createChatView } from '@/chat-view';
import { generateMockTranscript, mockMentionProvider } from '@/mock-transcript';
import type { ChatMessage, TranscriptTurn } from '@/model';
import { createChatState } from '@/state/chat-state';
import { pinTopMode, tailMode } from '@/state/scroll-mode';
import { storyViewport } from '@/stories/_harness/chat-host.css';

const meta: Meta = {
  title: 'Repro/BlankAfterSwitch',
  parameters: { layout: 'padded' },
};
export default meta;

type Story = StoryObj;

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeTranscript(label: string, count: number): TranscriptTurn[] {
  const turns = generateMockTranscript(count);
  const first = turns[0]?.items[0];
  if (first && first.kind === 'message' && first.role === 'user') {
    (first as ChatMessage).text = `[${label}] ${(first as ChatMessage).text}`;
  }
  return turns;
}

function lastUserId(turns: TranscriptTurn[]): string | undefined {
  for (let turnIndex = turns.length - 1; turnIndex >= 0; turnIndex--) {
    const turn = turns[turnIndex];
    for (let itemIndex = turn.items.length - 1; itemIndex >= 0; itemIndex--) {
      const it = turn.items[itemIndex];
      if (it.kind === 'message' && it.role === 'user') return it.id;
    }
  }
  return undefined;
}

// ── Harness ─────────────────────────────────────────────────────────────────

interface HarnessProps {
  /** Item count for the "long" tabs (indices 0 and 2). */
  longCount: number;
  /** Item count for the "short" tabs (indices 1 and 3). */
  shortCount: number;
  /** Tab auto-switch interval in ms (set < 16 to switch faster than a frame). */
  thrashMs: number;
  /** If > 0, seed each tab's history this many ms AFTER it is first activated. */
  asyncSeedMs: number;
  /** Keep an active (generating) turn open on each tab. */
  keepStreaming: boolean;
  /** 'tail' = follow newest; 'anchor' = park at last user message (top edge). */
  intent: 'tail' | 'anchor';
}

function Harness(props: HarnessProps) {
  const ctx = createChatContext({ theme: DEFAULT_THEME, mentionProvider: mockMentionProvider });
  onCleanup(() => ctx.dispose());

  // Four alternating long/short conversations — mirrors the desktop
  // per-conversation ChatState pattern.
  const counts = [props.longCount, props.shortCount, props.longCount, props.shortCount];
  const states = counts.map((_, i) => createChatState(ctx, { uri: `blank-repro-${i}` }));
  onCleanup(() => states.forEach((s) => s.dispose()));

  const fixtures = counts.map((c, i) => makeTranscript(`Tab ${i + 1}`, c));
  const seeded = new Set<number>();

  const seed = (i: number) => {
    if (seeded.has(i)) return;
    seeded.add(i);
    states[i].transcript.history.seed(fixtures[i]);
    const uid = lastUserId(fixtures[i]);
    states[i].scroll.set(props.intent === 'anchor' && uid ? pinTopMode(uid) : tailMode());
    if (props.keepStreaming) {
      states[i].transcript.activeTurn.set(
        {
          id: `live-turn-${i}`,
          seq: counts[i],
          initiator: 'agent',
          items: [
            {
              kind: 'message',
              id: `live-${i}`,
              seq: 0,
              role: 'assistant',
              text: 'streaming response…',
            },
          ],
        },
        'generating'
      );
    }
  };

  // Synchronous seeding (asyncSeedMs <= 0): populate everything up front.
  if (props.asyncSeedMs <= 0) counts.forEach((_, i) => seed(i));

  const scheduleSeed = (i: number) => {
    if (props.asyncSeedMs <= 0 || seeded.has(i)) return;
    setTimeout(() => seed(i), props.asyncSeedMs);
  };

  const [activeIdx, setActiveIdx] = createSignal(0);
  const [status, setStatus] = createSignal('idle');

  let viewport: HTMLElement | undefined;
  let container: HTMLDivElement | undefined;
  let view: ChatView | undefined;

  onMount(() => {
    if (!viewport) return;
    container = document.createElement('div');
    container.style.cssText = 'position: absolute; inset: 0;';
    viewport.appendChild(container);
    view = createChatView({
      context: ctx,
      state: states[0],
      parent: container,
      stickToBottom: true,
      pinUserMessages: true,
      composer: 'none',
    });
    onCleanup(() => view?.dispose());
    scheduleSeed(0);
  });

  // Swap model + (async) seed the newly active tab.
  createEffect(() => {
    const idx = activeIdx();
    if (view) view.setModel(states[idx]);
    scheduleSeed(idx);
  });

  // Blank detector: a few frames after a switch, count rendered rows. If the
  // active tab has data but 0 rows are mounted, that is the bug.
  createEffect(() => {
    const idx = activeIdx();
    let frames = 0;
    const check = () => {
      if (!container) return;
      frames++;
      const rows = container.querySelectorAll('[data-index]').length;
      const hasData = seeded.has(idx) && fixtures[idx].length > 0;
      const scroller = container.querySelector('[data-chat-scroll]') as HTMLElement | null;
      if (hasData && rows === 0) {
        setStatus(
          `⚠ BLANK on Tab ${idx + 1}: 0 rows / ${fixtures[idx].length} items · ` +
            `scrollTop=${Math.round(scroller?.scrollTop ?? -1)} ` +
            `scrollHeight=${Math.round(scroller?.scrollHeight ?? -1)} ` +
            `clientHeight=${Math.round(scroller?.clientHeight ?? -1)}`
        );
        return;
      }
      if (frames < 12) requestAnimationFrame(check);
      else if (hasData) setStatus(`ok: Tab ${idx + 1} rendered ${rows} rows`);
    };
    requestAnimationFrame(check);
  });

  const [thrashing, setThrashing] = createSignal(false);
  let timer: ReturnType<typeof setInterval> | undefined;
  const startThrash = () => {
    if (timer) return;
    setThrashing(true);
    timer = setInterval(() => setActiveIdx((i) => (i + 1) % states.length), props.thrashMs);
  };
  const stopThrash = () => {
    if (timer) clearInterval(timer);
    timer = undefined;
    setThrashing(false);
  };
  onCleanup(() => stopThrash());

  let sendCounter = 0;
  const sendMessage = () => {
    const idx = activeIdx();
    if (!seeded.has(idx)) seed(idx);
    const id = `sent-${idx}-${sendCounter++}`;
    states[idx].transcript.history.append([
      {
        id: `sent-turn-${id}`,
        seq: fixtures[idx].length + sendCounter,
        initiator: 'user',
        items: [{ kind: 'message', id, seq: 0, role: 'user', text: 'manual message' }],
      },
    ]);
  };

  const btn = (active = false) => ({
    padding: '4px 12px',
    'border-radius': '4px',
    border: active ? '2px solid #007aff' : '1px solid #ccc',
    background: active ? '#e8f0fe' : 'white',
    cursor: 'pointer',
  });

  return (
    <div
      style={{
        'font-family': 'system-ui, sans-serif',
        display: 'flex',
        'flex-direction': 'column',
        gap: '8px',
      }}
    >
      <div style={{ 'font-size': '13px', color: '#555', 'max-width': '640px' }}>
        <strong>Blank-after-switch repro.</strong> Thrash the tabs (or switch manually), then stop.
        If a tab with history shows no rows, the status line below reports <code>⚠ BLANK</code>.
        Then click <strong>Send message</strong> — the transcript should reappear, confirming the
        restore-on-named-event signature.
      </div>

      <div style={{ display: 'flex', gap: '4px', 'align-items': 'center', 'flex-wrap': 'wrap' }}>
        <For each={states}>
          {(_s, i) => (
            <button style={btn(activeIdx() === i())} onClick={() => setActiveIdx(i())}>
              Tab {i() + 1} ({counts[i()]})
            </button>
          )}
        </For>
        <div style={{ 'flex-grow': '1' }} />
        <button style={btn()} onClick={sendMessage}>
          Send message
        </button>
        <Show
          when={thrashing()}
          fallback={
            <button style={btn()} onClick={startThrash}>
              Auto-thrash
            </button>
          }
        >
          <button
            style={{ ...btn(), border: '1px solid #f00', background: '#fff0f0' }}
            onClick={stopThrash}
          >
            Stop
          </button>
        </Show>
      </div>

      <div
        style={{
          'font-size': '12px',
          'font-family': 'ui-monospace, monospace',
          padding: '6px 8px',
          'border-radius': '4px',
          background: status().startsWith('⚠') ? '#fff0f0' : '#f0fff0',
          color: status().startsWith('⚠') ? '#a00' : '#070',
          'min-height': '18px',
        }}
      >
        {status()}
      </div>

      <div
        class={storyViewport}
        style={{ position: 'relative', width: '640px', height: '480px', 'flex-shrink': '0' }}
        ref={(el) => {
          viewport = el;
        }}
      />
    </div>
  );
}

// ── Stories ───────────────────────────────────────────────────────────────────

const defaults: HarnessProps = {
  longCount: 40,
  shortCount: 3,
  thrashMs: 30,
  asyncSeedMs: 0,
  keepStreaming: false,
  intent: 'anchor',
};

/** History seeded asynchronously after each switch (mimics IPC history load). */
export const AsyncHistoryLoad: Story = {
  render: () => <Harness {...defaults} asyncSeedMs={60} />,
};

/** Switch away/back while a turn is streaming. */
export const SwitchWhileStreaming: Story = {
  render: () => <Harness {...defaults} keepStreaming />,
};

/** Long tab parked near the bottom → switch to a short tab (anchor out-of-range). */
export const AnchorLongToShort: Story = {
  render: () => <Harness {...defaults} thrashMs={20} />,
};

/** All knobs as Storybook controls. */
export const Playground: Story = {
  render: (args) => <Harness {...(args as unknown as HarnessProps)} />,
  args: defaults,
  argTypes: {
    longCount: { control: { type: 'number' } },
    shortCount: { control: { type: 'number' } },
    thrashMs: { control: { type: 'number' } },
    asyncSeedMs: { control: { type: 'number' } },
    keepStreaming: { control: { type: 'boolean' } },
    intent: { control: { type: 'inline-radio' }, options: ['tail', 'anchor'] },
  },
};
