/** Image-generation activity rendered through the compact generic tool row. */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { ChatToolCall, ToolNode, ToolStatus } from '@/model';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { ToolNodeStateMatrix } from '@/stories/_harness/state-matrix';
import { streamToolNode } from './tool-node-story-helpers';

const meta: Meta = {
  title: 'Rows/Tools/Image generation',
  component: ChatHost,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof ChatHost>;

function imageGenerationNode(status: ToolStatus, id = `image-generation-${status}`): ToolNode {
  return {
    kind: 'unknown-tool-call',
    id,
    seq: 0,
    toolCallId: id,
    title: 'Image generation',
    name: 'Image generation',
    toolKind: 'image-generation',
    status,
  };
}

export const StateMatrix: Story = {
  render: () => <ToolNodeStateMatrix build={(status) => imageGenerationNode(status)} />,
};

export const Streaming: Story = {
  render: () => (
    <ScriptedChat
      height={120}
      script={streamToolNode(imageGenerationNode('running', 'image-generation-stream'), [
        { afterMs: 1_200, status: 'done' },
      ])}
    />
  ),
};

const generatedPreview = `data:image/svg+xml,${encodeURIComponent(`
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800">
    <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ced9e6"/><stop offset="1" stop-color="#768aa3"/></linearGradient></defs>
    <rect width="800" height="800" fill="url(#g)"/>
    <circle cx="400" cy="360" r="210" fill="#f7f8fa" opacity=".8"/>
    <path d="M240 430 400 190l160 240-160 120z" fill="#3c4d60"/>
    <text x="400" y="680" text-anchor="middle" font-family="sans-serif" font-size="44" fill="#24303e">Generated concept</text>
  </svg>
`)}`;

export const GeneratedResult: Story = {
  render: () => {
    const tool: ChatToolCall = {
      kind: 'tool',
      id: 'image-generation-result',
      name: 'Generated image',
      activity: 'image-generation',
      status: 'done',
      outputAttachments: [
        { id: 'generated-concept', name: 'generated-concept.png', mimeType: 'image/png' },
      ],
    };
    return (
      <ChatHost
        height={400}
        items={[tool]}
        commands={{ resolveAttachment: async () => generatedPreview }}
      />
    );
  },
};
