/**
 * Streaming text smoothing stories — visualize the per-word fade-in animation
 * and the optional cadence smoother.
 *
 * Playground   — full controls: chunk delay, chunk size, fade duration, smoother.
 * WordFadeIn   — per-word fade at a steady word cadence (Part A only).
 * BurstyRaw / BurstySmoothed — same bursty feed, raw vs. cadence-smoothed.
 * SlowMotion   — slow word cadence so the fade is easy to inspect.
 */

import { assignInlineVars } from '@vanilla-extract/dynamic';
import { For, createMemo } from 'solid-js';
import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ScriptedChat } from '@/stories/_harness/chat-host';
import { streamMessage } from '@/stories/_harness/streaming/scenario';
import { streamWordDuration } from '@styles/effects.css';

// ── Sample texts ──────────────────────────────────────────────────────────────

const MULTI_PARAGRAPH = `\
Streaming text smoothing adds a per-word **fade-in** animation so that newly \
revealed words appear gracefully rather than popping in all at once.

Each word fades from opacity 0 to 1. Spaces and punctuation are preserved \
verbatim so the layout geometry is identical to the non-streaming case — the \
\`measure() === offsetHeight\` invariant is maintained.

The animation frontier advances after every render cycle, so on the next chunk \
only the freshly appended tail is animated. Words that were already visible on \
the previous render remain static.

> This technique is entirely **paint-only**: no reflow, no layout shift, and \
zero overhead once the message is committed.`;

const BURSTY_TEXT = `\
Bursty network: large chunks arrive at irregular intervals. The raw feed shows \
words popping in batches while the smoothed feed releases one word per tick for \
an even reading cadence.\n\nBoth feeds end with the same complete message.`;

// ── Playground ────────────────────────────────────────────────────────────────

type PlaygroundArgs = {
  /** Delay between dispatched chunks, ms. */
  chunkMs: number;
  /** Words per dispatched chunk (higher = burstier). */
  chunkSize: number;
  /** Fade-in animation duration, ms. */
  animationDurationMs: number;
  /** Wrap the transcript with the cadence smoother. */
  smoothed: boolean;
};

/**
 * Reads args reactively (storybook-solidjs reconciles the args store in place
 * rather than remounting). The fade duration is applied as a live CSS variable;
 * the timing/smoother args feed a keyed <Show> that re-creates ScriptedChat so
 * the stream restarts when they change.
 */
function StreamingPlayground(args: PlaygroundArgs) {
  // Restart key: changing any of these recreates the chat and replays the stream
  // (the <For> reconciles by value, so a changed key disposes + remounts the row).
  // animationDurationMs is intentionally excluded — it applies live via the CSS var.
  const restartKey = createMemo(() => `${args.chunkMs}|${args.chunkSize}|${args.smoothed}`);

  return (
    <div
      style={assignInlineVars({
        [streamWordDuration]: `${args.animationDurationMs}ms`,
      })}
    >
      <For each={[restartKey()]}>
        {() => (
          <ScriptedChat
            height={520}
            script={streamMessage({
              id: 'msg-playground',
              role: 'assistant',
              text: MULTI_PARAGRAPH,
              chunkMs: args.chunkMs,
              chunk: { mode: 'word', size: args.chunkSize },
            })}
          />
        )}
      </For>
    </div>
  );
}

const meta: Meta<PlaygroundArgs> = {
  title: 'Rows/Messages/Agent/StreamingText',
  parameters: { layout: 'centered' },
  render: (args) => <StreamingPlayground {...args} />,
  argTypes: {
    chunkMs: {
      control: { type: 'range', min: 0, max: 800, step: 10 },
      description: 'Delay between dispatched chunks (ms).',
    },
    chunkSize: {
      control: { type: 'range', min: 1, max: 12, step: 1 },
      description: 'Words per dispatched chunk — higher is burstier.',
    },
    animationDurationMs: {
      control: { type: 'range', min: 0, max: 1000, step: 10 },
      description: 'Per-word fade-in duration (ms). Applies live.',
    },
    smoothed: {
      control: 'boolean',
      description: 'Wrap the transcript with the cadence smoother.',
    },
  },
  args: {
    chunkMs: 10,
    chunkSize: 1,
    animationDurationMs: 200,
    smoothed: false,
  },
};
export default meta;

type Story = StoryObj<PlaygroundArgs>;

/** Full controls playground — adjust delay, chunk size, fade duration, smoother. */
export const Playground: Story = {};

// ── WordFadeIn ────────────────────────────────────────────────────────────────

/**
 * Streams a multi-paragraph assistant message word-by-word at a comfortable
 * reading pace. Demonstrates the per-word fade-in in isolation.
 */
export const WordFadeIn: Story = {
  name: 'Word Fade-In',
  render: () => (
    <ScriptedChat
      height={520}
      script={streamMessage({
        id: 'msg-fade',
        role: 'assistant',
        text: MULTI_PARAGRAPH,
        chunkMs: 55,
        chunk: { mode: 'word', size: 1 },
      })}
    />
  ),
};

// ── BurstyVsSmoothed ─────────────────────────────────────────────────────────

/**
 * Bursty feed rendered raw: chunks of 8 words arrive every 350 ms, so words pop
 * in visible batches.
 */
export const BurstyRaw: Story = {
  name: 'Bursty (Raw)',
  render: () => (
    <ScriptedChat
      height={260}
      script={streamMessage({
        id: 'msg-raw',
        role: 'assistant',
        text: BURSTY_TEXT,
        chunkMs: 350,
        chunk: { mode: 'word', size: 8 },
      })}
    />
  ),
};

/**
 * Same bursty feed wrapped with `createStreamSmoother`, which re-times the
 * deltas to a steady one-word-per-tick cadence.
 */
export const BurstySmoothed: Story = {
  name: 'Bursty (Smoothed)',
  render: () => (
    <ScriptedChat
      height={260}
      script={streamMessage({
        id: 'msg-smooth',
        role: 'assistant',
        text: BURSTY_TEXT,
        chunkMs: 350,
        chunk: { mode: 'word', size: 8 },
      })}
    />
  ),
};

// ── SlowMotion ────────────────────────────────────────────────────────────────

/**
 * Very slow word cadence so each per-word fade is clearly visible. Once the
 * message commits the text is static with no animation overhead.
 */
export const SlowMotion: Story = {
  name: 'Slow Motion (inspect animation)',
  render: () => (
    <ScriptedChat
      height={400}
      script={streamMessage({
        id: 'msg-slow',
        role: 'assistant',
        text: 'Each word appears one at a time with a visible fade animation. Once committed the text is static with no animation overhead.',
        chunkMs: 300,
        chunk: { mode: 'word', size: 1 },
      })}
    />
  ),
};
