/**
 * HorizontalRule block stories.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost } from '@/stories/_harness/chat-host';

const meta: Meta = {
  title: 'Rows/Markdown/HorizontalRule',
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
          text: 'Section A\n\n---\n\nSection B',
        },
      ]}
      height={160}
    />
  ),
};
