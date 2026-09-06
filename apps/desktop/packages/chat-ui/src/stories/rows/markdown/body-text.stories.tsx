/**
 * BodyText block stories.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { scenario, seedStep, streamMessage } from '@/stories/_harness/streaming/scenario';

const meta: Meta = {
  title: 'Rows/Markdown/BodyText',
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
          text: 'This is a regular body paragraph with **bold**, *italic*, and `inline code` text. It also has [a link](https://example.com) inline.',
        },
      ]}
      height={120}
    />
  ),
};

const BODY_TEXT_STREAMING = [
  'This is a regular body paragraph with **bold**, *italic*, and `inline code` text. ',
  'It also has [a link](https://example.com) inline.',
].join('');

export const Generating: Story = {
  render: () => (
    <ScriptedChat
      height={120}
      script={scenario(
        [seedStep([{ kind: 'message', id: 'u1', role: 'user', text: 'Write a paragraph' }])],
        streamMessage({ id: 'a1', text: BODY_TEXT_STREAMING, chunkMs: 40 })
      )}
    />
  ),
};
