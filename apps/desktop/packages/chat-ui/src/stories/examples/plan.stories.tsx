/**
 * Plan row examples — agent task list with mixed statuses and priorities.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { ChatPlanEntry } from '@/model';
import { ChatHost, ChatHostExpanded, ScriptedChat } from '@/stories/_harness/chat-host';
import type { ScriptStep } from '@/stories/_harness/chat-host';
import { applyTurnEvent } from '@/stories/_harness/turn-reducer';

const meta: Meta = {
  title: 'Examples/Plan',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

/** Plan with mixed statuses, pre-expanded to show the full task list. */
export const InProgress: Story = {
  render: () => (
    <ChatHostExpanded
      expandId="plan-1"
      items={[
        { kind: 'message', id: 'u1', role: 'user', text: 'Refactor the chat-ui package' },
        {
          kind: 'plan',
          id: 'plan-1',
          entries: [
            {
              content: 'Analyze existing codebase structure and identify components to modify',
              status: 'completed',
              priority: 'high',
            },
            {
              content: 'Extract duplicated utility functions into shared modules under `src/core/`',
              status: 'completed',
              priority: 'high',
            },
            {
              content:
                'Update `generateMockTranscript` to include diff, thought-role, and plan rows with varied content magnitude for representative perf sweeps',
              status: 'in_progress',
              priority: 'medium',
            },
            {
              content: 'Add HundredK Storybook story for 100k scroll-sweep performance testing',
              status: 'pending',
              priority: 'low',
            },
            {
              content: 'Run typecheck, lint, and test suite; verify all tests pass',
              status: 'pending',
              priority: 'high',
            },
          ],
        },
        {
          kind: 'message',
          id: 'a1',
          role: 'assistant',
          text: 'I have analyzed the codebase and extracted the utility functions. Now working on updating the mock transcript generator.',
        },
      ]}
      height={520}
    />
  ),
};

/** Plan collapsed by default — shows the capped preview window. Click to expand. */
export const AllCompleted: Story = {
  render: () => (
    <ChatHost
      items={[
        { kind: 'message', id: 'u1', role: 'user', text: 'Add the plan renderer' },
        {
          kind: 'plan',
          id: 'plan-2',
          entries: [
            {
              content: 'Add `ChatPlan` and `ChatPlanEntry` types to model.ts',
              status: 'completed',
              priority: 'high',
            },
            {
              content:
                'Create `plan.def.tsx` with collapsible layout and wrapped entry measurement',
              status: 'completed',
              priority: 'high',
            },
            {
              content: 'Create `Plan.tsx` with `PlanHeader` and `PlanList` components',
              status: 'completed',
              priority: 'medium',
            },
            {
              content: 'Register in REGISTRY and export from index.tsx',
              status: 'completed',
              priority: 'medium',
            },
            {
              content: 'Add mock-transcript coverage and focused example story',
              status: 'completed',
              priority: 'low',
            },
          ],
        },
        {
          kind: 'message',
          id: 'a1',
          role: 'assistant',
          text: 'All tasks completed! The plan renderer is now fully wired into the registry.',
        },
      ]}
      height={460}
    />
  ),
};

/** Plan with priority tints and varied entry lengths. */
export const MixedPriorities: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'plan',
          id: 'plan-3',
          entries: [
            {
              content: 'Fix critical authentication bug causing session invalidation on refresh',
              status: 'completed',
              priority: 'high',
            },
            {
              content: 'Update dependencies to resolve security advisories',
              status: 'in_progress',
              priority: 'high',
            },
            {
              content: 'Refactor the database migration scripts for better maintainability',
              status: 'pending',
              priority: 'medium',
            },
            {
              content: 'Update README',
              status: 'pending',
              priority: 'low',
            },
          ],
        },
      ]}
      height={300}
    />
  ),
};

/**
 * Streaming plan: tasks are appended one-by-one via `plan_update` dispatches.
 * Starts collapsed so the capped preview window auto-scrolls to each new task,
 * then settles on `turn_done`. Click the header to expand the full list.
 */
export const Streaming: Story = {
  render: () => {
    const STREAM_ENTRIES: ChatPlanEntry[] = [
      { content: 'Read the existing renderer and registry', status: 'completed', priority: 'high' },
      { content: 'Add the ChatPlan data model and types', status: 'completed', priority: 'high' },
      {
        content: 'Implement plan.def with collapsible layout and a capped preview window',
        status: 'in_progress',
        priority: 'medium',
      },
      {
        content: 'Wire the streaming plan_update transcript event',
        status: 'pending',
        priority: 'medium',
      },
      { content: 'Add tests and a Storybook example', status: 'pending', priority: 'low' },
    ];

    const planId = 'plan-stream';
    return (
      <ScriptedChat
        height={320}
        script={[
          {
            kind: 'call',
            fn: (api) => {
              const ev = {
                type: 'message_chunk' as const,
                role: 'user' as const,
                id: 'u1',
                text: 'Implement the plan renderer',
              };
              api.activeTurn.set(applyTurnEvent(api.activeTurn.get(), ev), 'generating');
            },
          },
          { kind: 'wait', ms: 400 },
          // Append tasks one-by-one (each update replaces the full list, ACP-style).
          ...STREAM_ENTRIES.flatMap((_, i): ScriptStep[] => [
            {
              kind: 'call',
              fn: (api) => {
                const ev = {
                  type: 'plan_update' as const,
                  id: planId,
                  entries: STREAM_ENTRIES.slice(0, i + 1),
                  streaming: true,
                };
                api.activeTurn.set(applyTurnEvent(api.activeTurn.get(), ev), 'generating');
              },
            },
            { kind: 'wait', ms: 700 },
          ]),
          // Settle the turn — clears the streaming flag.
          { kind: 'call', fn: (api) => api.activeTurn.commit('done') },
        ]}
      />
    );
  },
};
