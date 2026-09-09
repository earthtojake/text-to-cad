/**
 * Repro: scroll jump on expand in a short, reserve-active transcript.
 *
 * Symptoms (before fix):
 *   Expanding a thinking row in a transcript that:
 *     (a) has `pinUserMessages` active, and
 *     (b) has fewer items than one viewport height of content
 *   would snap the header out of view because readPhase re-derived intent from
 *   scrollTop on every idle frame. With the reserve active the transcript rests
 *   at `scrollTop === maxScrollTop`, so stuckIntent() was true, and the anchor
 *   set on the expand click was immediately overwritten with `{kind:'bottom'}`.
 *
 * After fix:
 *   readPhase only re-derives intent when `userDelta !== 0`, so the top-edge
 *   anchor set on the collapse-click survives the tween. The thinking header
 *   stays put as the row expands downward.
 *
 * Instructions:
 *   1. Open the "Short / ReserveActiveExpand" story.
 *   2. Click the thinking header to expand it.
 *   3. Verify the header stays at its current viewport position.
 *   4. Collapse it again — same thing, header stays put.
 */

import { DEFAULT_THEME } from '@core/theme';
import { onCleanup, onMount } from 'solid-js';
import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { createChatContext } from '@/chat-context';
import { createChatView } from '@/chat-view';
import { mockMentionProvider } from '@/mock-transcript';
import type { ChatItem, TranscriptTurn } from '@/model';
import { createChatState } from '@/state/chat-state';
import { storyViewport } from '@/stories/_harness/chat-host.css';

const meta: Meta = {
  title: 'Repro/ReserveActiveExpand',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

// ── Fixtures ──────────────────────────────────────────────────────────────────

const THINKING_BODY = `
This is a thinking block that takes up a moderate amount of vertical space.
It contains a few lines of reasoning text so it's large enough that expanding
it pushes content below the visible area. The key invariant being verified is
that the **header row stays put** while the content below it grows downward.

Reasoning step A: consider all available options.
Reasoning step B: evaluate trade-offs.
Reasoning step C: select the best approach.
`.trim();

function makeShortTranscript(): TranscriptTurn[] {
  const items = [
    {
      kind: 'message',
      id: 'user-1',
      role: 'user',
      text: 'Can you think through this problem for me?',
    },
    {
      kind: 'thinking',
      id: 'thinking-1',
      text: THINKING_BODY,
      status: 'done',
      startedAt: Date.now() - 2000,
      durationMs: 2000,
    },
    {
      kind: 'message',
      id: 'assistant-1',
      role: 'assistant',
      text: 'Sure! I have thought through it carefully and here is my answer.',
    },
  ] satisfies ChatItem[];
  return [
    {
      id: 'reserve-expand-turn',
      seq: 0,
      initiator: 'user',
      items: items.map((item, seq) => ({ ...item, seq })) as TranscriptTurn['items'],
      outcome: { kind: 'done' },
    },
  ];
}

// ── Story component ───────────────────────────────────────────────────────────

function ReserveExpandHarness() {
  const ctx = createChatContext({ theme: DEFAULT_THEME, mentionProvider: mockMentionProvider });
  onCleanup(() => ctx.dispose());

  const state = createChatState(ctx, { uri: 'story-reserve-expand' });
  onCleanup(() => state.dispose());

  // Seed a SHORT transcript — fewer rows than one viewport height.
  // With pinUserMessages this creates a non-zero activeTurnReserve so the
  // transcript rests at scrollTop === maxScrollTop even without streaming.
  state.transcript.history.seed(makeShortTranscript());

  let viewport: HTMLElement | undefined;

  onMount(() => {
    if (!viewport) return;
    const container = document.createElement('div');
    container.style.cssText = 'position: absolute; inset: 0;';
    viewport.appendChild(container);

    const view = createChatView({
      context: ctx,
      state,
      parent: container,
      stickToBottom: true,
      pinUserMessages: true,
      composer: 'none',
    });
    onCleanup(() => view.dispose());
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
        <strong>Reserve-active expand repro.</strong> Click the thinking header to expand /
        collapse. The header should stay at its current viewport position — it must NOT jump to the
        bottom or top of the scroll container.
      </div>
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
 * Short transcript with pinUserMessages. The transcript fits in less than one
 * viewport height, activating the reserve. Expand/collapse the thinking row —
 * the header must remain stable (no scroll jump).
 */
export const ReserveActiveExpand: Story = {
  render: () => <ReserveExpandHarness />,
};
