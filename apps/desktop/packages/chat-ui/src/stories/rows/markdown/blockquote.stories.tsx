/**
 * Blockquote block stories.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { scenario, seedStep, streamMessage } from '@/stories/_harness/streaming/scenario';

const meta: Meta = {
  title: 'Rows/Markdown/Blockquote',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

export const Default: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'assistant',
          text: '> This is a blockquote. It should have a left rail and indented text that wraps correctly at the container width.',
        },
      ]}
      height={120}
    />
  ),
};

const BLOCKQUOTE_STREAMING = [
  '> This is a blockquote. It should have a left rail and indented text ',
  'that wraps correctly at the container width.',
].join('');

export const Generating: Story = {
  render: () => (
    <ScriptedChat
      height={120}
      script={scenario(
        [seedStep([{ kind: 'message', id: 'u1', role: 'user', text: 'Add a note' }])],
        streamMessage({ id: 'a1', text: BLOCKQUOTE_STREAMING, chunkMs: 40 })
      )}
    />
  ),
};
