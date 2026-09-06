/**
 * Tool row stories — generic tool call in each status.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { ToolStateMatrix } from '@/stories/_harness/state-matrix';
import { scenario, seedStep, streamTool } from '@/stories/_harness/streaming/scenario';

const meta: Meta = {
  title: 'Rows/Tools/Tool',
  component: ChatHost,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof ChatHost>;

export const StateMatrix: Story = {
  render: () => (
    <ToolStateMatrix
      build={(status) => ({
        kind: 'tool',
        id: `t-matrix-${status}`,
        name: 'search',
        status,
        inputSummary: 'SolidJS virtualized list patterns',
      })}
    />
  ),
};

export const Running: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'tool',
          id: 't1',
          name: 'search',
          status: 'running',
          inputSummary: 'SolidJS virtualized list patterns',
        },
      ]}
      height={80}
    />
  ),
};

/** Streaming simulation: tool starts running then transitions to done. */
export const RunningStreamed: Story = {
  render: () => (
    <ScriptedChat
      height={120}
      script={scenario(
        [seedStep([{ kind: 'message', id: 'u1', role: 'user', text: 'Search for patterns' }])],
        streamTool({
          id: 't-stream',
          name: 'search',
          inputSummary: 'SolidJS virtualized list patterns',
          steps: [{ afterMs: 1200, status: 'done' }],
        })
      )}
    />
  ),
};

export const Done: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'tool',
          id: 't2',
          name: 'fetch_url',
          status: 'done',
          inputSummary: 'https://solidjs.com/docs/latest',
        },
      ]}
      height={80}
    />
  ),
};

export const Error: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'tool',
          id: 't3',
          name: 'web.run',
          status: 'error',
          error: 'Search provider returned a 503 response',
          inputSummary: 'latest ACP protocol specification',
        },
      ]}
      height={80}
    />
  ),
};

/** Permission request beneath a running generic tool call. */
export const RequestingPermission: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'tool',
          id: 't-perm',
          name: 'search',
          status: 'running',
          inputSummary: 'SolidJS virtualized list patterns',
        },
      ]}
      height={120}
    />
  ),
};
