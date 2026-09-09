/**
 * Thinking row stories — all states plus the active→done transition.
 *
 * Collapse semantics are inverted for thinking rows:
 *   default (no click) → not expanded: active shows preview, done shows header only
 *   after one click    → expanded:     both states show full prose body
 */

import type { TranscriptApi } from '@state/transcript';
import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { ChatItem, TranscriptTurn } from '@/model';
import type { ScriptStep } from '@/stories/_harness/chat-host';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import {
  scenario,
  seedStep,
  streamMessage,
  streamThinking,
} from '@/stories/_harness/streaming/scenario';

const meta: Meta = {
  title: 'Rows/Messages/Agent/Thinking',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

function turn(item: ChatItem): TranscriptTurn {
  return {
    id: `${item.id}:turn`,
    seq: 0,
    initiator: 'agent',
    items: [{ ...item, seq: 0 } as TranscriptTurn['items'][number]],
    outcome: { kind: 'done' },
  };
}

export const Generating: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'thinking',
          id: 'th1',
          status: 'thinking',
          text: 'Let me analyze the codebase structure first to understand the authentication flow...\n\nLooking at the middleware chain, I can see that session tokens are validated in three different places which creates redundancy.',
          startedAt: Date.now() - 12000,
        },
      ]}
      height={160}
    />
  ),
};

/**
 * Active preview renders real prose: bold, inline code, soft breaks, and
 * paragraph gaps. Visually verifies the preview uses the same BlockStack
 * pipeline as the expanded body (no raw-text fallback).
 */
export const GeneratingProsePreview: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'thinking',
          id: 'th-preview',
          status: 'thinking',
          text: [
            'Checking the **authentication** flow.',
            'Session tokens are validated in `middleware/session.ts`.',
            '',
            'Found a redundancy: the same `validateToken()` call appears in three places.',
            'Consolidating into a single middleware will fix this.',
          ].join('\n'),
          startedAt: Date.now() - 5000,
        },
      ]}
      height={200}
    />
  ),
};

export const GeneratingExpanded: Story = {
  render: () => {
    const script: ScriptStep[] = [
      {
        kind: 'call',
        fn: (api: TranscriptApi) => {
          api.history.seed([
            turn({
              kind: 'thinking',
              id: 'th1',
              status: 'thinking',
              text: 'Let me analyze the codebase structure first to understand the authentication flow...\n\nLooking at the middleware chain, I can see that session tokens are validated in three different places which creates redundancy.\n\nI will suggest consolidating validation into a single auth middleware.',
              startedAt: Date.now() - 8000,
            } as ChatItem),
          ]);
        },
      },
      { kind: 'wait', ms: 100 },
      {
        kind: 'call',
        fn: () => {
          const btn = document.querySelector('[data-collapse-id="th1"]') as HTMLElement;
          btn?.click();
        },
      },
    ];
    return <ScriptedChat script={script} height={280} />;
  },
};

export const DoneCollapsed: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'thinking',
          id: 'th1',
          status: 'done',
          text: 'I have analyzed the issue. The root cause is X.',
          startedAt: Date.now() - 30000,
          durationMs: 28000,
        },
      ]}
      height={80}
    />
  ),
};

export const DoneExpanded: Story = {
  render: () => {
    const script: ScriptStep[] = [
      {
        kind: 'call',
        fn: (api: TranscriptApi) => {
          api.history.seed([
            turn({
              kind: 'thinking',
              id: 'th1',
              status: 'done',
              text: 'First I looked at the authentication flow.\n\nThe session store is created in middleware/session.ts and uses Redis as a backend. The JWT approach would eliminate the need for this entirely.\n\nI considered three approaches:\n1. Pure JWT stateless\n2. JWT + Redis blacklist for revocation\n3. Opaque tokens with introspection\n\nOption 2 gives us the best balance of scalability and revocability.',
              startedAt: Date.now() - 30000,
              durationMs: 28000,
            } as ChatItem),
          ]);
        },
      },
      { kind: 'wait', ms: 100 },
      {
        kind: 'call',
        fn: () => {
          const btn = document.querySelector('[data-collapse-id="th1"]') as HTMLElement;
          btn?.click();
        },
      },
    ];
    return <ScriptedChat script={script} height={280} />;
  },
};

const TRANSITION_THINKING_TEXT =
  'Analyzing the codebase...\n\nChecking imports and exports...\n\nFound 3 circular dependencies.\n\nThe fix involves reordering module initialization.';

export const TransitionToDone: Story = {
  render: () => (
    <ScriptedChat
      height={200}
      script={streamThinking({ id: 'th1', text: TRANSITION_THINKING_TEXT, chunkMs: 80 })}
    />
  ),
};

/** Full turn: user prompt → thinking → streamed reply. */
export const ThenProse: Story = {
  render: () => (
    <ScriptedChat
      height={320}
      script={scenario(
        [seedStep([{ kind: 'message', id: 'u1', role: 'user', text: 'Optimize this function' }])],
        streamThinking({
          id: 'th1',
          text: 'Looking at the function...\nIt has O(n²) complexity due to nested loops.\nUsing a Map will reduce it to O(n).',
          chunkMs: 80,
        }),
        streamMessage({
          id: 'a1',
          text: 'The bottleneck is the nested loop. Use a `Map` to reduce to **O(n)**.',
          chunkMs: 80,
        })
      )}
    />
  ),
};

export const ExpandedProse: Story = {
  render: () => {
    const script: ScriptStep[] = [
      {
        kind: 'call',
        fn: (api: TranscriptApi) => {
          api.history.seed([
            turn({
              kind: 'thinking',
              id: 'th-prose',
              status: 'done',
              text: [
                '## Analysis',
                '',
                'The root issue is that `validateToken()` is called in **three** separate places.',
                'The fix is to consolidate into a single middleware.',
                '',
                '```ts',
                'export function authMiddleware(req, res, next) {',
                '  const token = req.headers.authorization?.split(" ")[1];',
                '  if (!validateToken(token)) return res.status(401).end();',
                '  next();',
                '}',
                '```',
                '',
                'This approach is both **simpler** and easier to audit.',
              ].join('\n'),
              startedAt: Date.now() - 12000,
              durationMs: 11000,
            } as ChatItem),
          ]);
        },
      },
      { kind: 'wait', ms: 100 },
      {
        kind: 'call',
        fn: () => {
          const btn = document.querySelector('[data-collapse-id="th-prose"]') as HTMLElement;
          btn?.click();
        },
      },
    ];
    return <ScriptedChat script={script} height={380} />;
  },
};
