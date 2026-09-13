/**
 * Web-fetch tool-call stories — ACP web-fetch-tool-call rendered through the generic tool row.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { ToolNode, ToolStatus } from '@/model';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { ToolNodeStateMatrix } from '@/stories/_harness/state-matrix';
import { streamToolNode } from './tool-node-story-helpers';

const meta: Meta = {
  title: 'Rows/Tools/WebFetch',
  component: ChatHost,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof ChatHost>;

function webFetchNode(status: ToolStatus, id = `web-fetch-${status}`): ToolNode {
  return {
    kind: 'web-fetch-tool-call',
    id,
    seq: 0,
    toolCallId: id,
    title: 'Fetch',
    status,
    url: 'https://solidjs.com/docs/latest',
    pageTitle: status === 'running' ? undefined : 'SolidJS Documentation',
  };
}

export const StateMatrix: Story = {
  render: () => <ToolNodeStateMatrix build={(status) => webFetchNode(status)} />,
};

export const Streaming: Story = {
  render: () => (
    <ScriptedChat
      height={120}
      script={streamToolNode(webFetchNode('running', 'web-fetch-stream'), [
        { afterMs: 900, inputSummary: 'https://solidjs.com/docs/latest' },
        { afterMs: 900, status: 'done' },
      ])}
    />
  ),
};
