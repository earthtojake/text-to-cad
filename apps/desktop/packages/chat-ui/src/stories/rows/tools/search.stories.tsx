/**
 * Search tool-call stories — ACP search-tool-call rendered through the generic tool row.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { ToolNode, ToolStatus } from '@/model';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { ToolNodeStateMatrix } from '@/stories/_harness/state-matrix';
import { streamToolNode } from './tool-node-story-helpers';

const meta: Meta = {
  title: 'Rows/Tools/Search',
  component: ChatHost,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof ChatHost>;

function searchNode(status: ToolStatus, id = `search-${status}`): ToolNode {
  const query = 'SolidJS virtualized list patterns';
  return {
    kind: 'search-tool-call',
    id,
    seq: 0,
    toolCallId: id,
    title: `Web search: ${query}`,
    status,
    query,
    scope: 'web',
    matchCount: status === 'running' ? undefined : 14,
  };
}

export const StateMatrix: Story = {
  render: () => <ToolNodeStateMatrix build={(status) => searchNode(status)} />,
};

export const Streaming: Story = {
  render: () => (
    <ScriptedChat
      height={120}
      script={streamToolNode(searchNode('running', 'search-stream'), [
        { afterMs: 800, inputSummary: 'SolidJS virtualized list patterns (14 matches)' },
        { afterMs: 800, status: 'done' },
      ])}
    />
  ),
};
