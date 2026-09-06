/**
 * BulletList block stories.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { scenario, seedStep, streamMessage } from '@/stories/_harness/streaming/scenario';

const meta: Meta = {
  title: 'Rows/Markdown/BulletList',
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
          text: 'Key points:\n\n- First item in the list\n- Second item with **bold**\n- Third item with `code`\n- Fourth item that is a bit longer to test wrapping behavior',
        },
      ]}
      height={220}
    />
  ),
};

const BULLET_LIST_STREAMING = [
  'Key points:\n\n',
  '- First item in the list\n',
  '- Second item with **bold**\n',
  '- Third item with `code`\n',
  '- Fourth item that is a bit longer to test wrapping behavior',
].join('');

export const Generating: Story = {
  render: () => (
    <ScriptedChat
      height={220}
      script={scenario(
        [seedStep([{ kind: 'message', id: 'u1', role: 'user', text: 'List the key points' }])],
        streamMessage({ id: 'a1', text: BULLET_LIST_STREAMING, chunkMs: 55 })
      )}
    />
  ),
};
