/**
 * Unknown tool-call stories — provider-specific tool calls rendered through the fallback row.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { ToolNode, ToolStatus } from '@/model';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { ToolNodeStateMatrix } from '@/stories/_harness/state-matrix';
import { streamToolNode } from './tool-node-story-helpers';

const meta: Meta = {
  title: 'Rows/Tools/Unknown',
  component: ChatHost,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof ChatHost>;

function unknownNode(status: ToolStatus, id = `unknown-${status}`): ToolNode {
  return {
    kind: 'unknown-tool-call',
    id,
    seq: 0,
    toolCallId: id,
    title: 'Vendor Tool',
    status,
    toolKind: 'vendor.lookup',
    name: 'vendor.lookup',
  };
}

export const StateMatrix: Story = {
  render: () => <ToolNodeStateMatrix build={(status) => unknownNode(status)} />,
};

export const Streaming: Story = {
  render: () => (
    <ScriptedChat
      height={120}
      script={streamToolNode(unknownNode('running', 'unknown-stream'), [
        { afterMs: 900, inputSummary: 'vendor.lookup' },
        { afterMs: 900, status: 'done' },
      ])}
    />
  ),
};
