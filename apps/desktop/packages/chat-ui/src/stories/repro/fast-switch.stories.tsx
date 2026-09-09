/**
 * Repro: blank transcript and stale pin after fast setModel swaps.
 *
 * Symptoms (before fix):
 *   - Switching between two tabs in rapid succession sometimes leaves the
 *     transcript blank (no rows rendered) until a new message arrives.
 *   - The pinned user-message header stops sticking after a few fast swaps:
 *     the overlay disappears even though the conversation has user messages.
 *
 * Root cause (before fix):
 *   The visible-row set and the pin state were computed by reactive memos
 *   (visibleIndexes, pinState) that consumed non-reactive virt mutations from
 *   setModel swaps. Effect ordering between the reset / incremental-committed /
 *   count-sync effects and the swap effect was fragile: the memo dependency
 *   graph could miss re-evaluations, leaving a stale (empty) row set.
 *
 * After fix (write-phase-owned geometry):
 *   - visible() and pin() are signals written exclusively by commit() in the
 *     scheduler's write phase.
 *   - A single invalidation-bridge effect arms the scheduler whenever any
 *     layout input changes — no per-memo dependency curation.
 *   - snapshotInto() captures the OUTGOING model's measured heights before
 *     committedUnitsArr is cleared, preventing heightmap pollution.
 *   - The swap effect in onMount only calls attach(next) + forceReconcile;
 *     all data teardown/rebuild is handled by component-scope effects that
 *     run first (Solid creation-order guarantee).
 *
 * Instructions:
 *   1. Open the "FastSwitch / RapidModelSwap" story.
 *   2. Click "Auto-thrash" to start automatic switching every 80 ms.
 *   3. Let it run for several seconds.
 *   4. Stop thrashing. The currently visible tab must show its full transcript
 *      rows and, if `pinUserMessages` is on, the pinned user-message header.
 *   5. Repeat with the "Manual" buttons to verify individual slow switches
 *      also work correctly.
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
import { tailMode } from '@/state/scroll-mode';
import { storyViewport } from '@/stories/_harness/chat-host.css';

const meta: Meta = {
  title: 'Repro/FastSwitch',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeTranscript(label: string, count = 12): TranscriptTurn[] {
  const turns = generateMockTranscript(count);
  // Prefix the first user message text so testers can confirm which tab is shown.
  const first = turns[0]?.items[0];
  if (first && first.kind === 'message' && first.role === 'user') {
    (first as ChatMessage).text = `[${label}] ${(first as ChatMessage).text}`;
  }
  return turns;
}

// ── Story component ───────────────────────────────────────────────────────────

interface Tab {
  label: string;
  state: ReturnType<typeof createChatState>;
}

function FastSwitchHarness(props: { autoThrash?: boolean }) {
  const ctx = createChatContext({ theme: DEFAULT_THEME, mentionProvider: mockMentionProvider });
  onCleanup(() => ctx.dispose());

  // Two independent ChatStates — mirrors the desktop per-conversation pattern.
  const stateA = createChatState(ctx, { uri: 'fast-switch-A' });
  const stateB = createChatState(ctx, { uri: 'fast-switch-B' });
  onCleanup(() => {
    stateA.dispose();
    stateB.dispose();
  });

  stateA.transcript.history.seed(makeTranscript('Tab A', 14));
  stateB.transcript.history.seed(makeTranscript('Tab B', 8));

  // Pre-set tail intent on both so the view starts at the bottom.
  stateA.scroll.set(tailMode());
  stateB.scroll.set(tailMode());

  const tabs: Tab[] = [
    { label: 'Tab A', state: stateA },
    { label: 'Tab B', state: stateB },
  ];

  const [activeIdx, setActiveIdx] = createSignal(0);

  let viewport: HTMLElement | undefined;
  let view: ChatView | undefined;

  onMount(() => {
    if (!viewport) return;
    const container = document.createElement('div');
    container.style.cssText = 'position: absolute; inset: 0;';
    viewport.appendChild(container);

    view = createChatView({
      context: ctx,
      state: stateA,
      parent: container,
      stickToBottom: true,
      pinUserMessages: true,
      composer: 'none',
    });
    onCleanup(() => view?.dispose());
  });

  // Switch tab via setModel when the active index changes.
  createEffect(() => {
    const idx = activeIdx();
    const tab = tabs[idx];
    if (view && tab) view.setModel(tab.state);
  });

  // Auto-thrash: switch tabs every 80 ms to stress-test the swap path.
  const [thrashing, setThrashing] = createSignal(props.autoThrash ?? false);
  let thrashTimer: ReturnType<typeof setInterval> | undefined;

  const startThrash = () => {
    if (thrashTimer) return;
    setThrashing(true);
    thrashTimer = setInterval(() => {
      setActiveIdx((i) => (i + 1) % tabs.length);
    }, 80);
  };

  const stopThrash = () => {
    if (thrashTimer) {
      clearInterval(thrashTimer);
      thrashTimer = undefined;
    }
    setThrashing(false);
  };

  onCleanup(() => stopThrash());

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
        <strong>Fast-switch repro.</strong> Switch tabs rapidly (or auto-thrash). After stopping,
        the active tab must show its full transcript and the pinned user-message header — never a
        blank viewport or a missing pin.
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: '4px' }}>
        <For each={tabs}>
          {(tab, i) => (
            <button
              style={{
                padding: '4px 12px',
                'border-radius': '4px',
                border: activeIdx() === i() ? '2px solid #007aff' : '1px solid #ccc',
                background: activeIdx() === i() ? '#e8f0fe' : 'white',
                cursor: 'pointer',
                'font-weight': activeIdx() === i() ? 'bold' : 'normal',
              }}
              onClick={() => setActiveIdx(i())}
            >
              {tab.label}
            </button>
          )}
        </For>

        <div style={{ 'flex-grow': '1' }} />

        <Show
          when={thrashing()}
          fallback={
            <button
              style={{
                padding: '4px 12px',
                'border-radius': '4px',
                border: '1px solid #ccc',
                background: 'white',
                cursor: 'pointer',
              }}
              onClick={startThrash}
            >
              Auto-thrash
            </button>
          }
        >
          <button
            style={{
              padding: '4px 12px',
              'border-radius': '4px',
              border: '1px solid #f00',
              background: '#fff0f0',
              cursor: 'pointer',
            }}
            onClick={stopThrash}
          >
            Stop
          </button>
        </Show>
      </div>

      {/* Single chat viewport — the view.setModel path drives it */}
      <div
        class={storyViewport}
        style={{ width: '640px', height: '480px' }}
        ref={(el) => {
          viewport = el;
        }}
      />
    </div>
  );
}

/**
 * Two ChatStates mounted on one ChatView, switched manually.
 * After each switch the transcript must render immediately (no blank state).
 */
export const RapidModelSwap: Story = {
  render: () => <FastSwitchHarness />,
};

/**
 * Same setup but with automatic 80 ms tab switching for several seconds.
 * After stopping, the pinned header and full row set must be intact.
 */
export const AutoThrash: Story = {
  render: () => <FastSwitchHarness autoThrash />,
};
