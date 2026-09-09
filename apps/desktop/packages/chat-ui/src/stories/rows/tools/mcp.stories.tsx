/**
 * MCP tool-call stories — ACP mcp-tool-call rendered through the generic tool row.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { ToolNode, ToolStatus } from '@/model';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { ToolNodeStateMatrix } from '@/stories/_harness/state-matrix';
import { streamToolNode } from './tool-node-story-helpers';

const meta: Meta = {
  title: 'Rows/Tools/MCP',
  component: ChatHost,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof ChatHost>;

function mcpNode(status: ToolStatus, id = `mcp-${status}`): ToolNode {
  return {
    kind: 'mcp-tool-call',
    id,
    seq: 0,
    toolCallId: id,
    title: 'MCP',
    status,
    server: 'linear',
    tool: 'searchIssues',
  };
}

export const StateMatrix: Story = {
  render: () => <ToolNodeStateMatrix build={(status) => mcpNode(status)} />,
};

export const Streaming: Story = {
  render: () => (
    <ScriptedChat
      height={120}
      script={streamToolNode(mcpNode('running', 'mcp-stream'), [
        { afterMs: 900, inputSummary: 'linear.searchIssues' },
        { afterMs: 900, status: 'done' },
      ])}
    />
  ),
};
